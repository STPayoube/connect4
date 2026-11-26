import asyncio
import copy
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from schemas import AiInfo, GameConfig, GameStateResponse, MoveRecord, PlayerInfo
from weakc4 import AI, Connect4, Player


class GameError(Exception):
    """Domain error with an associated HTTP status code."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class UndoSnapshot:
    grid: list[list[int]]
    current_player: int
    status: str
    winner: Optional[int]
    winning_cells: list[list[int]]
    move_history_len: int
    last_ai_info: Optional[dict]
    mover_type: str


@dataclass
class GameSession:
    session_id: str
    config: GameConfig
    c4: Connect4
    player_objs: dict[int, Player]
    player_meta: dict[int, PlayerInfo]
    status: str = "playing"
    winner: Optional[int] = None
    winning_cells: list[list[int]] = field(default_factory=list)
    move_history: list[MoveRecord] = field(default_factory=list)
    snapshots: list[UndoSnapshot] = field(default_factory=list)
    last_ai_info: Optional[dict] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)
    on_change: Optional[Callable[["GameSession"], None]] = None

    def _notify(self):
        if self.on_change:
            self.on_change(self)

    def _capture_snapshot(self, mover_type: str):
        self.snapshots.append(
            UndoSnapshot(
                grid=[row[:] for row in self.c4.grid],
                current_player=self.c4.current_player,
                status=self.status,
                winner=self.winner,
                winning_cells=[cell[:] for cell in self.winning_cells],
                move_history_len=len(self.move_history),
                last_ai_info=copy.deepcopy(self.last_ai_info),
                mover_type=mover_type,
            )
        )

    def _evaluate_outcome(self):
        winner, cells = self.c4.check_win()
        if winner is not None:
            self.status = "win"
            self.winner = winner
            self.winning_cells = cells
        elif self.c4.is_full():
            self.status = "draw"
            self.winner = None
            self.winning_cells = []
        else:
            self.status = "playing"
            self.winner = None
            self.winning_cells = []

    def _advance_turn(self):
        self.c4.current_player = 2 if self.c4.current_player == 1 else 1

    def _apply_ai_turn(self) -> MoveRecord:
        if self.status != "playing":
            raise GameError("Game is already finished.", status_code=409)
        active_id = self.c4.current_player
        active_meta = self.player_meta[active_id]
        if active_meta.type != "ai":
            raise GameError(
                f"It is currently Player {active_id} ({active_meta.name})'s human turn.",
                status_code=409,
            )

        self._capture_snapshot("ai")
        ai_player: AI = self.player_objs[active_id]
        result = ai_player.choose_move(self.c4)
        self.last_ai_info = result["ai_info"]

        record = MoveRecord(
            ply=len(self.move_history) + 1,
            player=active_id,
            player_name=active_meta.name,
            player_type="ai",
            row=result["row"],
            col=result["col"],
            ai_info=AiInfo(**result["ai_info"]),
        )
        self.move_history.append(record)
        self._evaluate_outcome()
        if self.status == "playing":
            self._advance_turn()
        self.updated_at = time.time()
        return record

    def play_human_move(self, col: int, auto_ai_reply: bool = True) -> list[MoveRecord]:
        with self.lock:
            if self.status != "playing":
                raise GameError("Game is already finished.", status_code=409)

            active_id = self.c4.current_player
            active_meta = self.player_meta[active_id]
            if active_meta.type != "human":
                raise GameError(
                    f"Cannot make a human move on Player {active_id} ({active_meta.name})'s AI turn.",
                    status_code=409,
                )

            if col < 0 or col >= self.c4.col:
                raise GameError(
                    f"Column {col} is out of bounds (0..{self.c4.col - 1}).",
                    status_code=400,
                )
            if self.c4.get_drop_row(col) is None:
                raise GameError(f"Column {col} is full.", status_code=400)

            self._capture_snapshot("human")
            human_player = self.player_objs[active_id]
            row, played_col = human_player.play_column(self.c4, col)

            human_record = MoveRecord(
                ply=len(self.move_history) + 1,
                player=active_id,
                player_name=active_meta.name,
                player_type="human",
                row=row,
                col=played_col,
                ai_info=None,
            )
            self.move_history.append(human_record)
            self._evaluate_outcome()
            if self.status == "playing":
                self._advance_turn()

            applied = [human_record]

            if (
                auto_ai_reply
                and self.status == "playing"
                and self.player_meta[self.c4.current_player].type == "ai"
            ):
                ai_record = self._apply_ai_turn()
                applied.append(ai_record)

            self.updated_at = time.time()
        self._notify()
        return applied

    def step_ai_move(self) -> list[MoveRecord]:
        with self.lock:
            applied = [self._apply_ai_turn()]
        self._notify()
        return applied

    def _can_undo(self) -> bool:
        if not self.snapshots:
            return False
        if self.config.mode == "human_vs_ai":
            return any(s.mover_type == "human" for s in self.snapshots)
        return True

    def undo(self) -> None:
        with self.lock:
            if not self._can_undo():
                raise GameError("No moves to undo.", status_code=400)

            if self.config.mode == "human_vs_ai":
                snap = self.snapshots.pop()
                while snap.mover_type == "ai" and self.snapshots:
                    snap = self.snapshots.pop()
            else:
                snap = self.snapshots.pop()

            self.c4.grid = snap.grid
            self.c4.current_player = snap.current_player
            self.status = snap.status
            self.winner = snap.winner
            self.winning_cells = snap.winning_cells
            self.move_history = self.move_history[: snap.move_history_len]
            self.last_ai_info = snap.last_ai_info
            self.updated_at = time.time()
        self._notify()

    def to_response(self, moves_applied: Optional[list[MoveRecord]] = None) -> GameStateResponse:
        return GameStateResponse(
            session_id=self.session_id,
            username=self.config.username,
            config=self.config,
            players={str(k): v for k, v in self.player_meta.items()},
            grid=[row[:] for row in self.c4.grid],
            current_player=self.c4.current_player,
            valid_columns=self.c4.get_valid_columns() if self.status == "playing" else [],
            status=self.status,
            winner=self.winner,
            winning_cells=[cell[:] for cell in self.winning_cells],
            last_move=self.move_history[-1] if self.move_history else None,
            moves_applied=moves_applied or [],
            move_history=list(self.move_history),
            can_undo=self._can_undo(),
            ai_info=AiInfo(**self.last_ai_info) if self.last_ai_info else None,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


def _resolve_starting_player(raw_starter, random_start: bool) -> tuple[int, bool]:
    if raw_starter == "random" or random_start:
        return random.choice([1, 2]), True
    return int(raw_starter), False


def _build_session(
    session_id: str,
    config: GameConfig,
    on_change: Optional[Callable[[GameSession], None]] = None,
) -> GameSession:
    if config.mode == "human_vs_ai":
        ai_label = f"AI ({config.ai_level.capitalize()})"
        if config.human_player == 1:
            p1 = Player(config.username, 1, "X")
            p2 = AI(ai_label, 2, "O", depth=config.ai_depth, level=config.ai_level)
            meta1 = PlayerInfo(id=1, name=config.username, type="human")
            meta2 = PlayerInfo(
                id=2, name=ai_label, type="ai", level=config.ai_level, depth=config.ai_depth
            )
        else:
            p1 = AI(ai_label, 1, "X", depth=config.ai_depth, level=config.ai_level)
            p2 = Player(config.username, 2, "O")
            meta1 = PlayerInfo(
                id=1, name=ai_label, type="ai", level=config.ai_level, depth=config.ai_depth
            )
            meta2 = PlayerInfo(id=2, name=config.username, type="human")
    elif config.mode == "player_vs_player":
        p1_name = config.username
        p2_name = config.player2_name if config.player2_name != config.username else f"{config.player2_name} (P2)"
        p1 = Player(p1_name, 1, "X")
        p2 = Player(p2_name, 2, "O")
        meta1 = PlayerInfo(id=1, name=p1_name, type="human")
        meta2 = PlayerInfo(id=2, name=p2_name, type="human")
    else:
        lvl1 = config.ai_level
        lvl2 = config.ai2_level or config.ai_level
        p1 = AI(f"AI 1 ({lvl1.capitalize()})", 1, "X", depth=config.ai_depth, level=lvl1)
        p2 = AI(f"AI 2 ({lvl2.capitalize()})", 2, "O", depth=config.ai2_depth, level=lvl2)
        meta1 = PlayerInfo(id=1, name=p1.name, type="ai", level=lvl1, depth=config.ai_depth)
        meta2 = PlayerInfo(id=2, name=p2.name, type="ai", level=lvl2, depth=config.ai2_depth)

    c4_players = {
        1: [meta1.name, 1, "X"],
        2: [meta2.name, 2, "O"],
    }
    c4 = Connect4(
        players=c4_players,
        current_player=config.starting_player,
        row=config.rows,
        col=config.cols,
        align=config.align,
        verbose=False,
    )

    return GameSession(
        session_id=session_id,
        config=config,
        c4=c4,
        player_objs={1: p1, 2: p2},
        player_meta={1: meta1, 2: meta2},
        on_change=on_change,
    )


class SessionManager:
    def __init__(self, ttl_seconds: int = 7200, max_sessions: int = 500):
        self._sessions: dict[str, GameSession] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._sub_lock = threading.Lock()

    def subscribe_admin(
        self, loop: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.Queue, Callable[[], None]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        entry = (loop, queue)
        with self._sub_lock:
            self._subscribers.add(entry)

        def unsubscribe():
            with self._sub_lock:
                self._subscribers.discard(entry)

        return queue, unsubscribe

    def _broadcast(self, event_type: str, payload: Any):
        with self._sub_lock:
            subs = list(self._subscribers)

        def _enqueue(q: asyncio.Queue, item: dict):
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(item)
            except Exception:
                pass

        message = {"event": event_type, "data": payload}
        for loop, queue in subs:
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(_enqueue, queue, message)
                except RuntimeError:
                    pass

    def _broadcast_session(self, session: GameSession):
        with session.lock:
            snapshot = session.to_response().model_dump()
        self._broadcast("session_update", snapshot)

    def _evict_stale(self):
        now = time.time()
        expired = [
            sid
            for sid, sess in self._sessions.items()
            if now - sess.updated_at > self._ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]
            self._broadcast("session_delete", {"session_id": sid})

        if len(self._sessions) >= self._max_sessions:
            oldest = sorted(self._sessions.items(), key=lambda item: item[1].updated_at)
            for sid, _ in oldest[: len(self._sessions) - self._max_sessions + 1]:
                del self._sessions[sid]
                self._broadcast("session_delete", {"session_id": sid})

    def list_all(self) -> list[dict]:
        with self._lock:
            self._evict_stale()
            sessions_copy = list(self._sessions.values())

        results = []
        for sess in sessions_copy:
            with sess.lock:
                results.append(sess.to_response().model_dump())
        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    def create(
        self,
        raw_payload: dict,
        auto_play_opening_ai: bool = False,
    ) -> GameStateResponse:
        starter, was_random = _resolve_starting_player(
            raw_payload.get("starting_player", 1),
            bool(raw_payload.get("random_start", False)),
        )
        cfg_data = {**raw_payload, "starting_player": starter, "random_start": was_random}
        config = GameConfig(**cfg_data)
        session_id = str(uuid.uuid4())
        session = _build_session(session_id, config, on_change=self._broadcast_session)

        with self._lock:
            self._evict_stale()
            self._sessions[session_id] = session

        applied: list[MoveRecord] = []
        if (
            auto_play_opening_ai
            and session.status == "playing"
            and session.player_meta[session.c4.current_player].type == "ai"
        ):
            applied = session.step_ai_move()
        else:
            self._broadcast_session(session)

        with session.lock:
            return session.to_response(moves_applied=applied)

    def get(self, session_id: str) -> GameSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise GameError(f"Game session '{session_id}' not found.", status_code=404)
            session.updated_at = time.time()
            return session

    def reset(
        self,
        session_id: str,
        overrides: dict,
        auto_play_opening_ai: bool = False,
    ) -> GameStateResponse:
        existing = self.get(session_id)
        merged = existing.config.model_dump()

        # Respect explicit level vs depth overrides cleanly
        if overrides.get("ai_level") is not None and overrides.get("ai_depth") is None:
            merged["ai_depth"] = None
        if overrides.get("ai_depth") is not None and overrides.get("ai_level") is None:
            merged["ai_level"] = None
        if overrides.get("ai2_level") is not None and overrides.get("ai2_depth") is None:
            merged["ai2_depth"] = None
        if overrides.get("ai2_depth") is not None and overrides.get("ai2_level") is None:
            merged["ai2_level"] = None

        for key, value in overrides.items():
            if value is not None:
                merged[key] = value

        if overrides.get("align") is None:
            merged["align"] = min(merged["align"], merged["rows"], merged["cols"])
        if overrides.get("ai_level") is not None and overrides.get("ai2_level") is None and overrides.get("ai2_depth") is None:
            merged["ai2_level"] = merged["ai_level"]
            merged["ai2_depth"] = None
        elif overrides.get("ai_depth") is not None and overrides.get("ai2_depth") is None and overrides.get("ai2_level") is None:
            merged["ai2_depth"] = merged["ai_depth"]
            merged["ai2_level"] = None

        starter_input = overrides.get("starting_player", merged["starting_player"])
        random_flag = bool(
            overrides.get("random_start")
            if overrides.get("random_start") is not None
            else (starter_input == "random")
        )
        starter, was_random = _resolve_starting_player(starter_input, random_flag)
        merged["starting_player"] = starter
        merged["random_start"] = was_random

        try:
            new_config = GameConfig(**merged)
        except Exception as exc:
            raise GameError(str(exc), status_code=422) from exc

        new_session = _build_session(session_id, new_config, on_change=self._broadcast_session)
        with self._lock:
            self._sessions[session_id] = new_session

        applied: list[MoveRecord] = []
        if (
            auto_play_opening_ai
            and new_session.status == "playing"
            and new_session.player_meta[new_session.c4.current_player].type == "ai"
        ):
            applied = new_session.step_ai_move()
        else:
            self._broadcast_session(new_session)

        with new_session.lock:
            return new_session.to_response(moves_applied=applied)

    def delete(self, session_id: str) -> None:
        with self._lock:
            if session_id not in self._sessions:
                raise GameError(f"Game session '{session_id}' not found.", status_code=404)
            del self._sessions[session_id]
        self._broadcast("session_delete", {"session_id": session_id})
