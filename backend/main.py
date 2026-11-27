import asyncio
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values, load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from database import Database
from game_manager import GameError, SessionManager
from schemas import (
    AdminLoginRequest,
    BlacklistEntryRequest,
    CreateGameRequest,
    CreatePrizeGameRequest,
    CreateRoomRequest,
    GameStateResponse,
    HumanMoveRequest,
    JoinRoomRequest,
    ResetGameRequest,
    RoomJoinResponse,
    RoomMoveRequest,
    RoomRematchRequest,
    UpdateSessionDifficultyRequest,
    UpdateWinAPrizeConfigRequest,
)

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

logger = logging.getLogger("connect4")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
if ADMIN_PASSWORD == "admin123":
    logger.warning(
        "ADMIN_PASSWORD is using the default local value. Set ADMIN_PASSWORD in .env on production VPS!"
    )


def _get_admin_password() -> str:
    if ENV_PATH.is_file():
        file_pwd = dotenv_values(ENV_PATH).get("ADMIN_PASSWORD")
        if file_pwd is not None and file_pwd.strip():
            return file_pwd.strip()
    return os.getenv("ADMIN_PASSWORD", ADMIN_PASSWORD).strip()


ADMIN_TOKEN_TTL_SECONDS = 86400
_admin_tokens: dict[str, float] = {}


def _verify_admin_token(token: Optional[str]) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    expires_at = _admin_tokens.get(token)
    if expires_at is None or time.time() > expires_at:
        _admin_tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="Invalid or expired admin session.")
    return token


def require_admin(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    return _verify_admin_token(token)


app = FastAPI(
    title="Connect 4 — WeakC4 API",
    description="REST API, Online Friend Rooms, Win-a-Prize mode, Stats & Live Admin monitor.",
    version="3.0.0",
)

cors_origins_env = os.getenv("CORS_ORIGINS", "").strip()
if not cors_origins_env:
    cors_origins_env = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()
sessions = SessionManager(db=db)


def _assert_allowed_usernames(*names: Optional[str]) -> None:
    for name in names:
        if not name:
            continue
        blocked, reason = db.is_username_blocked(name)
        if blocked:
            msg = "This username is not allowed. Please choose another username."
            if reason:
                msg = f"Username not allowed ({reason}). Please choose another username."
            raise HTTPException(status_code=403, detail=msg)


@app.exception_handler(GameError)
async def handle_game_error(_request: Request, exc: GameError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# --- Standard Game Endpoints ---


@app.post("/api/games", response_model=GameStateResponse, status_code=201)
def create_game(payload: CreateGameRequest):
    _assert_allowed_usernames(
        payload.username,
        payload.player2_name if payload.mode == "player_vs_player" else None,
    )
    raw = payload.model_dump(exclude={"auto_play_opening_ai"})
    return sessions.create(raw, auto_play_opening_ai=payload.auto_play_opening_ai)


@app.get("/api/games/{session_id}", response_model=GameStateResponse)
def get_game(session_id: str):
    session = sessions.get(session_id)
    with session.lock:
        return session.to_response()


@app.post("/api/games/{session_id}/reset", response_model=GameStateResponse)
def reset_game(session_id: str, payload: ResetGameRequest = ResetGameRequest()):
    _assert_allowed_usernames(payload.username, payload.player2_name)
    overrides = payload.model_dump(exclude={"auto_play_opening_ai"})
    return sessions.reset(
        session_id,
        overrides=overrides,
        auto_play_opening_ai=payload.auto_play_opening_ai,
    )


@app.post("/api/games/{session_id}/move", response_model=GameStateResponse)
def make_human_move(session_id: str, payload: HumanMoveRequest):
    session = sessions.get(session_id)
    if session.channel == "online_pvp":
        raise HTTPException(status_code=400, detail="Use /api/rooms/{code}/move for online rooms.")
    applied = session.play_human_move(col=payload.col, auto_ai_reply=payload.auto_ai_reply)
    with session.lock:
        return session.to_response(moves_applied=applied)


@app.post("/api/games/{session_id}/ai-move", response_model=GameStateResponse)
def step_ai_move(session_id: str):
    session = sessions.get(session_id)
    applied = session.step_ai_move()
    with session.lock:
        return session.to_response(moves_applied=applied)


@app.post("/api/games/{session_id}/undo", response_model=GameStateResponse)
def undo_move(session_id: str):
    session = sessions.get(session_id)
    session.undo()
    with session.lock:
        return session.to_response()


@app.delete("/api/games/{session_id}", status_code=204)
def delete_game(session_id: str):
    sessions.delete(session_id)
    return None


# --- Special Win-a-Prize Endpoints (/winaprize) ---


@app.get("/api/winaprize/config")
def get_public_winaprize_config():
    cfg = db.get_winaprize_config()
    # Deliberately omit ai_level from public endpoint so admin live difficulty switching stays stealthy
    return {
        "enabled": cfg["enabled"],
        "rows": cfg["rows"],
        "cols": cfg["cols"],
        "align": cfg["align"],
        "allow_undo": cfg["allow_undo"],
        "title": cfg["title"],
        "subtitle": cfg["subtitle"],
    }


@app.post("/api/winaprize/games", response_model=GameStateResponse, status_code=201)
def create_winaprize_game(payload: CreatePrizeGameRequest):
    _assert_allowed_usernames(payload.username)
    cfg = db.get_winaprize_config()
    if not cfg.get("enabled", True):
        raise HTTPException(
            status_code=403,
            detail="The Win a Prize challenge is currently closed by the administrator.",
        )

    raw = {
        "rows": cfg["rows"],
        "cols": cfg["cols"],
        "align": cfg["align"],
        "mode": "human_vs_ai",
        "ai_level": cfg["ai_level"],
        "starting_player": "random" if cfg.get("random_start") else cfg["starting_player"],
        "human_player": cfg["human_player"],
        "random_start": bool(cfg.get("random_start", False)),
        "username": payload.username,
    }
    return sessions.create(
        raw,
        auto_play_opening_ai=payload.auto_play_opening_ai,
        channel="winaprize",
        allow_undo=bool(cfg.get("allow_undo", False)),
    )


# --- Online Friend PvP Room Endpoints (/game#XXXXXX) ---


@app.post("/api/rooms", response_model=RoomJoinResponse, status_code=201)
def create_room(payload: CreateRoomRequest):
    _assert_allowed_usernames(payload.username)
    state, token, seat = sessions.create_room(
        username=payload.username,
        rows=payload.rows,
        cols=payload.cols,
        align=payload.align,
        starting_player=payload.starting_player,
        random_start=payload.random_start,
    )
    return RoomJoinResponse(
        room_code=state.room_code,
        seat=seat,
        player_token=token,
        game=state,
    )


@app.get("/api/rooms/{room_code}", response_model=GameStateResponse)
def get_room_state(room_code: str):
    session = sessions.get_room(room_code)
    with session.lock:
        return session.to_response()


@app.post("/api/rooms/{room_code}/join", response_model=RoomJoinResponse)
def join_room(room_code: str, payload: JoinRoomRequest):
    _assert_allowed_usernames(payload.username)
    state, token, seat = sessions.join_room(room_code, payload.username)
    return RoomJoinResponse(
        room_code=state.room_code,
        seat=seat,
        player_token=token,
        game=state,
    )


@app.post("/api/rooms/{room_code}/move", response_model=GameStateResponse)
def room_move(room_code: str, payload: RoomMoveRequest):
    return sessions.play_room_move(room_code, payload.col, payload.player_token)


@app.post("/api/rooms/{room_code}/rematch", response_model=GameStateResponse)
def room_rematch(room_code: str, payload: RoomRematchRequest):
    return sessions.rematch_room(room_code, payload.player_token, payload.random_start)


@app.get("/api/rooms/{room_code}/stream")
async def room_stream(room_code: str, request: Request):
    session = sessions.get_room(room_code)
    code = session.room_code
    loop = asyncio.get_running_loop()
    queue, unsubscribe = sessions.subscribe_room(code, loop)

    async def event_generator():
        try:
            with session.lock:
                initial = session.to_response().model_dump()
            yield f"event: init\ndata: {json.dumps(initial)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Admin Control Panel Endpoints ---


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginRequest):
    expected = _get_admin_password()
    if not hmac.compare_digest(payload.password.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid admin password.")
    now = time.time()
    for expired_tok in [t for t, exp in _admin_tokens.items() if now > exp]:
        _admin_tokens.pop(expired_tok, None)
    token = secrets.token_urlsafe(32)
    _admin_tokens[token] = now + ADMIN_TOKEN_TTL_SECONDS
    return {"token": token, "expires_in": ADMIN_TOKEN_TTL_SECONDS}


@app.post("/api/admin/logout", status_code=204)
def admin_logout(token: str = Depends(require_admin)):
    _admin_tokens.pop(token, None)
    return None


@app.get("/api/admin/sessions")
def admin_list_sessions(_token: str = Depends(require_admin)):
    return {"sessions": sessions.list_all()}


@app.patch("/api/admin/sessions/{session_id}/difficulty", response_model=GameStateResponse)
def admin_update_session_difficulty(
    session_id: str,
    payload: UpdateSessionDifficultyRequest,
    _token: str = Depends(require_admin),
):
    return sessions.update_session_difficulty(
        session_id,
        ai_level=payload.ai_level,
        ai2_level=payload.ai2_level,
    )


@app.delete("/api/admin/sessions/{session_id}", status_code=204)
def admin_delete_session(session_id: str, _token: str = Depends(require_admin)):
    sessions.delete(session_id)
    return None


@app.get("/api/admin/winaprize/config")
def admin_get_winaprize_config(_token: str = Depends(require_admin)):
    return {
        "config": db.get_winaprize_config(),
        "live_prize_games": sessions.count_live_winaprize(),
    }


@app.put("/api/admin/winaprize/config")
def admin_update_winaprize_config(
    payload: UpdateWinAPrizeConfigRequest,
    _token: str = Depends(require_admin),
):
    cfg_dict = payload.model_dump(exclude={"apply_to_live_games"})
    saved = db.save_winaprize_config(cfg_dict)
    updated_live = 0
    if payload.apply_to_live_games:
        updated_live = sessions.update_winaprize_live_difficulty(saved["ai_level"])
    return {
        "config": saved,
        "updated_live_games": updated_live,
        "live_prize_games": sessions.count_live_winaprize(),
    }


@app.get("/api/admin/stats")
def admin_get_stats(_token: str = Depends(require_admin)):
    return db.get_stats()


@app.get("/api/admin/history")
def admin_list_history(
    channel: Optional[str] = Query(default=None),
    outcome: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _token: str = Depends(require_admin),
):
    return db.list_game_records(
        channel=channel, outcome=outcome, search=search, limit=limit, offset=offset
    )


@app.get("/api/admin/history/{record_id}")
def admin_get_history_record(record_id: int, _token: str = Depends(require_admin)):
    record = db.get_game_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Game record not found.")
    return record


@app.delete("/api/admin/history/{record_id}", status_code=204)
def admin_delete_history_record(record_id: int, _token: str = Depends(require_admin)):
    if not db.delete_game_record(record_id):
        raise HTTPException(status_code=404, detail="Game record not found.")
    return None


@app.get("/api/admin/blacklist")
def admin_list_blacklist(_token: str = Depends(require_admin)):
    return {"entries": db.list_blacklist()}


@app.post("/api/admin/blacklist", status_code=201)
def admin_add_blacklist(
    payload: BlacklistEntryRequest, _token: str = Depends(require_admin)
):
    try:
        entry = db.add_blacklist_entry(
            pattern=payload.pattern, match_type=payload.match_type, reason=payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return entry


@app.delete("/api/admin/blacklist/{entry_id}", status_code=204)
def admin_delete_blacklist(entry_id: int, _token: str = Depends(require_admin)):
    if not db.delete_blacklist_entry(entry_id):
        raise HTTPException(status_code=404, detail="Blacklist entry not found.")
    return None


@app.get("/api/admin/stream")
async def admin_stream(request: Request, token: str = Query(...)):
    _verify_admin_token(token)
    loop = asyncio.get_running_loop()
    queue, unsubscribe = sessions.subscribe_admin(loop)

    async def event_generator():
        try:
            initial = sessions.list_all()
            yield f"event: init\ndata: {json.dumps({'sessions': initial})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Optional single-process static frontend serving (with SPA fallback for /admin, /winaprize, /game)
if os.getenv("SERVE_STATIC", "false").lower() in ("1", "true", "yes"):
    dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    assets_dir = dist_dir / "assets"
    if not dist_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"Frontend dist not found at {dist_dir}")
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    dist_root = dist_dir.resolve()

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path:
            candidate = (dist_root / full_path).resolve()
            if candidate.is_relative_to(dist_root) and candidate.is_file():
                return FileResponse(str(candidate))
        return FileResponse(str(dist_root / "index.html"))
