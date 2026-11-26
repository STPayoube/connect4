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

from game_manager import GameError, SessionManager
from schemas import (
    AdminLoginRequest,
    CreateGameRequest,
    GameStateResponse,
    HumanMoveRequest,
    ResetGameRequest,
)

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

logger = logging.getLogger("connect4")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
if ADMIN_PASSWORD == "admin123":
    logger.warning("ADMIN_PASSWORD is using the default local value. Set ADMIN_PASSWORD in .env on production VPS!")


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
    description="REST API & live Admin monitor for playing Connect 4 against weakc4.py.",
    version="2.0.0",
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

sessions = SessionManager()


@app.exception_handler(GameError)
async def handle_game_error(_request: Request, exc: GameError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/games", response_model=GameStateResponse, status_code=201)
def create_game(payload: CreateGameRequest):
    raw = payload.model_dump(exclude={"auto_play_opening_ai"})
    return sessions.create(raw, auto_play_opening_ai=payload.auto_play_opening_ai)


@app.get("/api/games/{session_id}", response_model=GameStateResponse)
def get_game(session_id: str):
    session = sessions.get(session_id)
    with session.lock:
        return session.to_response()


@app.post("/api/games/{session_id}/reset", response_model=GameStateResponse)
def reset_game(session_id: str, payload: ResetGameRequest = ResetGameRequest()):
    overrides = payload.model_dump(exclude={"auto_play_opening_ai"})
    return sessions.reset(
        session_id,
        overrides=overrides,
        auto_play_opening_ai=payload.auto_play_opening_ai,
    )


@app.post("/api/games/{session_id}/move", response_model=GameStateResponse)
def make_human_move(session_id: str, payload: HumanMoveRequest):
    session = sessions.get(session_id)
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


@app.delete("/api/admin/sessions/{session_id}", status_code=204)
def admin_delete_session(session_id: str, _token: str = Depends(require_admin)):
    sessions.delete(session_id)
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


# Optional single-process static frontend serving (with SPA fallback for /admin)
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
