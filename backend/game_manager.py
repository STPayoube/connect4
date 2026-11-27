import asyncio
import copy
import random
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from database import Database
from schemas import AiInfo, GameConfig, GameStateResponse, MoveRecord, PlayerInfo
from weakc4 import AI, LEVEL_TO_DEPTH, Connect4, Player

LEVEL_LABELS_FR = {
    "easy": "Facile",
    "medium": "Moyen",
    "hard": "Difficile",
    "impossible": "Impossible",
}


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


def _resize_grid_checked(
    grid: list[list[int]],
    new_rows: int,
    new_cols: int,
    label: str = "la partie",
) -> tuple[list[list[int]], int]:
    """
    Copy existing board tokens into a new (new_rows x new_cols) grid while preserving
    bottom-anchored gravity. Raises GameError(409) if shrinking would cut off placed tokens.
    """
    old_rows = len(grid)
    old_cols = len(grid[0]) if old_rows else 0

    blocked_top_rows = []
    if new_rows < old_rows:
        cut_rows = old_rows - new_rows
        for r in range(cut_rows):
            if any(grid[r][c] != 0 for c in range(old_cols)):
                blocked_top_rows.append(r + 1)

    blocked_cols = []
    if new_cols < old_cols:
        for c in range(new_cols, old_cols):
            if any(grid[r][c] != 0 for r in range(old_rows)):
                blocked_cols.append(c + 1)

    if blocked_top_rows or blocked_cols:
        reasons = []
        if blocked_top_rows:
            reasons.append(
                f"des pions occupent déjà les lignes supérieures ({', '.join(map(str, blocked_top_rows))})"
            )
        if blocked_cols:
            reasons.append(
                f"des pions occupent déjà les colonnes ({', '.join(map(str, blocked_cols))})"
            )
        raise GameError(
            f"Impossible de réduire {label} en {new_rows}×{new_cols} : {' et '.join(reasons)}.",
            status_code=409,
        )

    row_offset = new_rows - old_rows
    new_grid = [[0 for _ in range(new_cols)] for _ in range(new_rows)]
    for r in range(old_rows):
        for c in range(old_cols):
            val = grid[r][c]
            if val != 0:
                nr = r + row_offset
                if 0 <= nr < new_rows and 0 <= c < new_cols:
                    new_grid[nr][c] = val

    return new_grid, row_offset


@dataclass
class GameSession:
    session_id: str
    config: GameConfig
    c4: Connect4
    player_objs: dict[int, Player]
    player_meta: dict[int, PlayerInfo]
    channel: str = "normal"
    room_code: Optional[str] = None
    waiting_for_opponent: bool = False
    allow_undo: bool = True
    player_tokens: dict[int, str] = field(default_factory=dict)
    status: str = "playing"
    winner: Optional[int] = None
    winning_cells: list[list[int]] = field(default_factory=list)
    move_history: list[MoveRecord] = field(default_factory=list)
    snapshots: list[UndoSnapshot] = field(default_factory=list)
    last_ai_info: Optional[dict] = None
    persisted: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)
    on_change: Optional[Callable[["GameSession"], None]] = None
    on_finish: Optional[Callable[["GameSession"], None]] = None

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

    def _evaluate_outcome(self) -> bool:
        """Evaluate win/draw. Returns True if the game just transitioned to finished."""
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
            return False

        if not self.persisted:
            self.persisted = True
            return True
        return False

    def _advance_turn(self):
        self.c4.current_player = 2 if self.c4.current_player == 1 else 1

    def check_resize_possible(self, new_rows: int, new_cols: int, new_align: int) -> None:
        """Dry-run validation used before batch-updating live games."""
        if not (4 <= new_rows <= 10 and 4 <= new_cols <= 10):
            raise GameError("Les dimensions doivent être comprises entre 4 et 10.", status_code=400)
        if new_align < 3 or new_align > min(new_rows, new_cols):
            raise GameError(
                f"L'alignement ({new_align}) ne peut pas dépasser {min(new_rows, new_cols)}.",
                status_code=400,
            )
        with self.lock:
            _resize_grid_checked(
                self.c4.grid, new_rows, new_cols, label=f"la partie de {self.config.username}"
            )

    def apply_live_config(
        self,
        ai_level: Optional[str] = None,
        ai2_level: Optional[str] = None,
        rows: Optional[int] = None,
        cols: Optional[int] = None,
        align: Optional[int] = None,
        allow_undo: Optional[bool] = None,
    ) -> None:
        """
        Live-update board dimensions (copying existing checkers with gravity), alignment,
        undo permission, and/or AI difficulty while the game is actively being played.
        """
        just_finished = False
        with self.lock:
            new_rows = self.c4.row if rows is None else int(rows)
            new_cols = self.c4.col if cols is None else int(cols)
            new_align = self.c4.align if align is None else int(align)

            if not (4 <= new_rows <= 10 and 4 <= new_cols <= 10):
                raise GameError(
                    "Les dimensions doivent être comprises entre 4 et 10.", status_code=400
                )
            if new_align < 3 or new_align > min(new_rows, new_cols):
                raise GameError(
                    f"L'alignement ({new_align}) ne peut pas dépasser {min(new_rows, new_cols)}.",
                    status_code=400,
                )

            dimensions_changed = (
                new_rows != self.c4.row or new_cols != self.c4.col or new_align != self.c4.align
            )

            if dimensions_changed:
                new_grid, row_offset = _resize_grid_checked(
                    self.c4.grid,
                    new_rows,
                    new_cols,
                    label=f"la partie de {self.config.username}",
                )
                # Copy databoard into a clean Connect4 instance with updated dimensions/align
                new_c4 = Connect4(
                    players=copy.deepcopy(self.c4.players),
                    current_player=self.c4.current_player,
                    row=new_rows,
                    col=new_cols,
                    align=new_align,
                    verbose=False,
                )
                new_c4.grid = new_grid
                self.c4 = new_c4

                self.config.rows = new_rows
                self.config.cols = new_cols
                self.config.align = new_align

                # Shift recorded move coordinates so last-move highlight stays aligned
                if row_offset != 0:
                    self.move_history = [
                        m.model_copy(update={"row": m.row + row_offset})
                        for m in self.move_history
                    ]

                # Resize compatible snapshots (drop any snapshot that wouldn't fit)
                resized_snaps = []
                for snap in self.snapshots:
                    try:
                        sg, s_off = _resize_grid_checked(snap.grid, new_rows, new_cols)
                        resized_snaps.append(
                            UndoSnapshot(
                                grid=sg,
                                current_player=snap.current_player,
                                status=snap.status,
                                winner=snap.winner,
                                winning_cells=[[r + s_off, c] for r, c in snap.winning_cells],
                                move_history_len=snap.move_history_len,
                                last_ai_info=snap.last_ai_info,
                                mover_type=snap.mover_type,
                            )
                        )
                    except GameError:
                        pass
                self.snapshots = resized_snaps

            if allow_undo is not None:
                self.allow_undo = bool(allow_undo)

            if ai_level is not None and self.config.mode != "player_vs_player":
                depth1 = LEVEL_TO_DEPTH[ai_level]
                lvl2 = (
                    ai2_level
                    if (self.config.mode == "ai_vs_ai" and ai2_level)
                    else ai_level
                )
                depth2 = LEVEL_TO_DEPTH[lvl2]

                self.config.ai_level = ai_level
                self.config.ai_depth = depth1
                self.config.ai2_level = lvl2
                self.config.ai2_depth = depth2

                for pid in (1, 2):
                    obj = self.player_objs[pid]
                    meta = self.player_meta[pid]
                    if isinstance(obj, AI):
                        target_lvl = (
                            lvl2 if (self.config.mode == "ai_vs_ai" and pid == 2) else ai_level
                        )
                        target_depth = (
                            depth2 if (self.config.mode == "ai_vs_ai" and pid == 2) else depth1
                        )
                        obj.level = target_lvl
                        obj.depth = target_depth
                        meta.level = target_lvl
                        meta.depth = target_depth
                        lvl_label = LEVEL_LABELS_FR.get(target_lvl, target_lvl.capitalize())
                        if self.channel == "winaprize":
                            meta.name = "IA Puissance 4"
                        elif self.config.mode == "ai_vs_ai":
                            meta.name = f"IA {pid} ({lvl_label})"
                        else:
                            meta.name = f"IA ({lvl_label})"
                        obj.name = meta.name
                        self.c4.players[pid][0] = meta.name

            if dimensions_changed:
                just_finished = self._evaluate_outcome()

            self.updated_at = time.time()

        if just_finished and self.on_finish:
            self.on_finish(self)
        self._notify()

    def set_ai_level(self, ai_level: str, ai2_level: Optional[str] = None) -> None:
        if self.config.mode == "player_vs_player":
            raise GameError(
                "Impossible de changer la difficulté IA sur une partie Joueur vs Joueur.",
                status_code=400,
            )
        self.apply_live_config(ai_level=ai_level, ai2_level=ai2_level)

    def _apply_ai_turn(self) -> tuple[MoveRecord, bool]:
        if self.status != "playing":
            raise GameError("La partie est déjà terminée.", status_code=409)
        active_id = self.c4.current_player
        active_meta = self.player_meta[active_id]
        if active_meta.type != "ai":
            raise GameError(
                f"C'est actuellement au tour de {active_meta.name} (humain).",
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
        just_finished = self._evaluate_outcome()
        if self.status == "playing":
            self._advance_turn()
        self.updated_at = time.time()
        return record, just_finished

    def play_human_move(self, col: int, auto_ai_reply: bool = True) -> list[MoveRecord]:
        just_finished = False
        with self.lock:
            if self.waiting_for_opponent:
                raise GameError("En attente du Joueur 2 dans le salon.", status_code=409)
            if self.status != "playing":
                raise GameError("La partie est déjà terminée.", status_code=409)

            active_id = self.c4.current_player
            active_meta = self.player_meta[active_id]
            if active_meta.type != "human":
                raise GameError(
                    f"Impossible de jouer pendant le tour de {active_meta.name}.",
                    status_code=409,
                )

            if col < 0 or col >= self.c4.col:
                raise GameError(
                    f"La colonne {col + 1} est hors limites (1..{self.c4.col}).",
                    status_code=400,
                )
            if self.c4.get_drop_row(col) is None:
                raise GameError(f"La colonne {col + 1} est pleine.", status_code=400)

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
            just_finished = self._evaluate_outcome()
            if self.status == "playing":
                self._advance_turn()

            applied = [human_record]

            if (
                auto_ai_reply
                and self.status == "playing"
                and self.player_meta[self.c4.current_player].type == "ai"
            ):
                ai_record, ai_finished = self._apply_ai_turn()
                just_finished = just_finished or ai_finished
                applied.append(ai_record)

            self.updated_at = time.time()

        if just_finished and self.on_finish:
            self.on_finish(self)
        self._notify()
        return applied

    def step_ai_move(self) -> list[MoveRecord]:
        with self.lock:
            record, just_finished = self._apply_ai_turn()
        if just_finished and self.on_finish:
            self.on_finish(self)
        self._notify()
        return [record]

    def _can_undo(self) -> bool:
        if not self.allow_undo or not self.snapshots:
            return False
        if self.config.mode == "human_vs_ai":
            return any(s.mover_type == "human" for s in self.snapshots)
        return True

    def undo(self) -> None:
        with self.lock:
            if not self._can_undo():
                raise GameError("Annulation désactivée ou aucun coup à annuler.", status_code=400)

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
            if self.status == "playing":
                self.persisted = False
            self.updated_at = time.time()
        self._notify()

    def to_response(
        self,
        moves_applied: Optional[list[MoveRecord]] = None,
        for_admin: bool = False,
    ) -> GameStateResponse:
        players_payload = {}
        for k, meta in self.player_meta.items():
            if self.channel == "winaprize" and not for_admin and meta.type == "ai":
                players_payload[str(k)] = PlayerInfo(
                    id=meta.id, name="IA Puissance 4", type="ai", level=None, depth=None
                )
            else:
                players_payload[str(k)] = meta

        hide_ai_details = self.channel == "winaprize" and not for_admin
        history_out = (
            [
                m.model_copy(update={"ai_info": None}) if m.ai_info is not None else m
                for m in self.move_history
            ]
            if hide_ai_details
            else list(self.move_history)
        )
        applied_out = (
            [
                m.model_copy(update={"ai_info": None}) if m.ai_info is not None else m
                for m in (moves_applied or [])
            ]
            if hide_ai_details
            else (moves_applied or [])
        )

        return GameStateResponse(
            session_id=self.session_id,
            channel=self.channel,
            room_code=self.room_code,
            waiting_for_opponent=self.waiting_for_opponent,
            allow_undo=self.allow_undo,
            username=self.config.username,
            config=self.config,
            players=players_payload,
            grid=[row[:] for row in self.c4.grid],
            current_player=self.c4.current_player,
            valid_columns=(
                self.c4.get_valid_columns()
                if (self.status == "playing" and not self.waiting_for_opponent)
                else []
            ),
            status=self.status,
            winner=self.winner,
            winning_cells=[cell[:] for cell in self.winning_cells],
            last_move=history_out[-1] if history_out else None,
            moves_applied=applied_out,
            move_history=history_out,
            can_undo=self._can_undo(),
            ai_info=(
                None
                if hide_ai_details
                else (AiInfo(**self.last_ai_info) if self.last_ai_info else None)
            ),
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
    channel: str = "normal",
    room_code: Optional[str] = None,
    waiting_for_opponent: bool = False,
    allow_undo: bool = True,
    player_tokens: Optional[dict[int, str]] = None,
    on_change: Optional[Callable[[GameSession], None]] = None,
    on_finish: Optional[Callable[[GameSession], None]] = None,
) -> GameSession:
    if config.mode == "human_vs_ai":
        lvl_fr = LEVEL_LABELS_FR.get(config.ai_level, config.ai_level.capitalize())
        ai_label = "IA Puissance 4" if channel == "winaprize" else f"IA ({lvl_fr})"
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
        if waiting_for_opponent:
            p2_name = "En attente d'un ami…"
        else:
            p2_name = (
                config.player2_name
                if config.player2_name != config.username
                else f"{config.player2_name} (J2)"
            )
        p1 = Player(p1_name, 1, "X")
        p2 = Player(p2_name, 2, "O")
        meta1 = PlayerInfo(id=1, name=p1_name, type="human")
        meta2 = PlayerInfo(id=2, name=p2_name, type="human")
    else:
        lvl1 = config.ai_level
        lvl2 = config.ai2_level or config.ai_level
        l1_fr = LEVEL_LABELS_FR.get(lvl1, lvl1.capitalize())
        l2_fr = LEVEL_LABELS_FR.get(lvl2, lvl2.capitalize())
        p1 = AI(f"IA 1 ({l1_fr})", 1, "X", depth=config.ai_depth, level=lvl1)
        p2 = AI(f"IA 2 ({l2_fr})", 2, "O", depth=config.ai2_depth, level=lvl2)
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
        channel=channel,
        room_code=room_code,
        waiting_for_opponent=waiting_for_opponent,
        allow_undo=allow_undo,
        player_tokens=player_tokens or {},
        on_change=on_change,
        on_finish=on_finish,
    )


class SessionManager:
    def __init__(
        self,
        db: Optional[Database] = None,
        ttl_seconds: int = 7200,
        max_sessions: int = 500,
    ):
        self.db = db
        self._sessions: dict[str, GameSession] = {}
        self._rooms: dict[str, str] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions

        self._admin_subs: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._room_subs: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._session_subs: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._sub_lock = threading.Lock()

    # --- Pub/Sub (Admin, Online Rooms, and Individual Live Sessions for WebSockets & SSE) ---

    def subscribe_admin(
        self, loop: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.Queue, Callable[[], None]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=120)
        entry = (loop, queue)
        with self._sub_lock:
            self._admin_subs.add(entry)

        def unsubscribe():
            with self._sub_lock:
                self._admin_subs.discard(entry)

        return queue, unsubscribe

    def subscribe_room(
        self, room_code: str, loop: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.Queue, Callable[[], None]]:
        code = room_code.strip().upper()
        queue: asyncio.Queue = asyncio.Queue(maxsize=60)
        entry = (loop, queue)
        with self._sub_lock:
            self._room_subs.setdefault(code, set()).add(entry)

        def unsubscribe():
            with self._sub_lock:
                subs = self._room_subs.get(code)
                if subs:
                    subs.discard(entry)
                    if not subs:
                        self._room_subs.pop(code, None)

        return queue, unsubscribe

    def subscribe_session(
        self, session_id: str, loop: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.Queue, Callable[[], None]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=60)
        entry = (loop, queue)
        with self._sub_lock:
            self._session_subs.setdefault(session_id, set()).add(entry)

        def unsubscribe():
            with self._sub_lock:
                subs = self._session_subs.get(session_id)
                if subs:
                    subs.discard(entry)
                    if not subs:
                        self._session_subs.pop(session_id, None)

        return queue, unsubscribe

    @staticmethod
    def _push_to_subs(
        subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]],
        event_type: str,
        payload: Any,
    ):
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

    def _broadcast_admin(self, event_type: str, payload: Any):
        with self._sub_lock:
            subs = list(self._admin_subs)
        self._push_to_subs(subs, event_type, payload)

    def _broadcast_room(self, room_code: str, event_type: str, payload: Any):
        with self._sub_lock:
            subs = list(self._room_subs.get(room_code, ()))
        if subs:
            self._push_to_subs(subs, event_type, payload)

    def _broadcast_session(self, session_id: str, event_type: str, payload: Any):
        with self._sub_lock:
            subs = list(self._session_subs.get(session_id, ()))
        if subs:
            self._push_to_subs(subs, event_type, payload)

    def _on_session_change(self, session: GameSession):
        with session.lock:
            admin_snapshot = session.to_response(for_admin=True).model_dump()
            player_snapshot = session.to_response(for_admin=False).model_dump()
            room_code = session.room_code
            sid = session.session_id

        self._broadcast_admin("session_update", admin_snapshot)
        self._broadcast_session(sid, "game_update", player_snapshot)
        if room_code:
            self._broadcast_room(room_code, "room_update", player_snapshot)

    def _on_session_finish(self, session: GameSession):
        if self.db is None:
            return
        with session.lock:
            snapshot = session.to_response(for_admin=True).model_dump()
        self.db.save_finished_game(snapshot)
        self._broadcast_admin("stats_update", {"session_id": session.session_id})

    # --- Eviction & Listing ---

    def _evict_stale(self):
        now = time.time()
        expired = [
            sid
            for sid, sess in self._sessions.items()
            if now - sess.updated_at > self._ttl_seconds
        ]
        for sid in expired:
            sess = self._sessions.pop(sid)
            if sess.room_code:
                self._rooms.pop(sess.room_code, None)
            self._broadcast_admin("session_delete", {"session_id": sid})

        if len(self._sessions) >= self._max_sessions:
            oldest = sorted(self._sessions.items(), key=lambda item: item[1].updated_at)
            for sid, _ in oldest[: len(self._sessions) - self._max_sessions + 1]:
                sess = self._sessions.pop(sid)
                if sess.room_code:
                    self._rooms.pop(sess.room_code, None)
                self._broadcast_admin("session_delete", {"session_id": sid})

    def list_all(self) -> list[dict]:
        with self._lock:
            self._evict_stale()
            sessions_copy = list(self._sessions.values())

        results = []
        for sess in sessions_copy:
            with sess.lock:
                results.append(sess.to_response(for_admin=True).model_dump())
        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    # --- Standard & Prize Sessions ---

    def create(
        self,
        raw_payload: dict,
        auto_play_opening_ai: bool = False,
        channel: str = "normal",
        allow_undo: bool = True,
    ) -> GameStateResponse:
        starter, was_random = _resolve_starting_player(
            raw_payload.get("starting_player", 1),
            bool(raw_payload.get("random_start", False)),
        )
        cfg_data = {**raw_payload, "starting_player": starter, "random_start": was_random}
        config = GameConfig(**cfg_data)
        session_id = str(uuid.uuid4())
        session = _build_session(
            session_id,
            config,
            channel=channel,
            allow_undo=allow_undo,
            on_change=self._on_session_change,
            on_finish=self._on_session_finish,
        )

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
            self._on_session_change(session)

        with session.lock:
            return session.to_response(moves_applied=applied)

    def get(self, session_id: str) -> GameSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise GameError(f"Session '{session_id}' introuvable.", status_code=404)
            session.updated_at = time.time()
            return session

    def reset(
        self,
        session_id: str,
        overrides: dict,
        auto_play_opening_ai: bool = False,
    ) -> GameStateResponse:
        existing = self.get(session_id)
        if existing.channel == "online_pvp":
            raise GameError("Utilisez /api/rooms/{code}/rematch pour les salons en ligne.", status_code=400)

        merged = existing.config.model_dump()

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

        new_session = _build_session(
            session_id,
            new_config,
            channel=existing.channel,
            allow_undo=existing.allow_undo,
            on_change=self._on_session_change,
            on_finish=self._on_session_finish,
        )
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
            self._on_session_change(new_session)

        with new_session.lock:
            return new_session.to_response(moves_applied=applied)

    def delete(self, session_id: str) -> None:
        with self._lock:
            sess = self._sessions.pop(session_id, None)
            if sess is None:
                raise GameError(f"Session '{session_id}' introuvable.", status_code=404)
            if sess.room_code:
                self._rooms.pop(sess.room_code, None)
        self._broadcast_admin("session_delete", {"session_id": session_id})

    # --- Live Mid-Game Modification (Difficulty, Board Size, Alignment, Undo) ---

    def update_session_live_config(
        self,
        session_id: str,
        ai_level: Optional[str] = None,
        ai2_level: Optional[str] = None,
        rows: Optional[int] = None,
        cols: Optional[int] = None,
        align: Optional[int] = None,
        allow_undo: Optional[bool] = None,
    ) -> GameStateResponse:
        session = self.get(session_id)
        session.apply_live_config(
            ai_level=ai_level,
            ai2_level=ai2_level,
            rows=rows,
            cols=cols,
            align=align,
            allow_undo=allow_undo,
        )
        with session.lock:
            return session.to_response(for_admin=True)

    def update_session_difficulty(
        self, session_id: str, ai_level: str, ai2_level: Optional[str] = None
    ) -> GameStateResponse:
        session = self.get(session_id)
        session.set_ai_level(ai_level, ai2_level=ai2_level)
        with session.lock:
            return session.to_response(for_admin=True)

    def update_winaprize_live_sessions(
        self,
        ai_level: str,
        rows: int,
        cols: int,
        align: int,
        allow_undo: bool,
    ) -> int:
        with self._lock:
            live_prize = [
                sess
                for sess in self._sessions.values()
                if sess.channel == "winaprize" and sess.status == "playing"
            ]

        # Validate EVERY active /winaprize game first so no partial update occurs on collision
        for sess in live_prize:
            sess.check_resize_possible(rows, cols, align)

        for sess in live_prize:
            sess.apply_live_config(
                ai_level=ai_level,
                rows=rows,
                cols=cols,
                align=align,
                allow_undo=allow_undo,
            )
        return len(live_prize)

    def count_live_winaprize(self) -> int:
        with self._lock:
            return sum(
                1
                for sess in self._sessions.values()
                if sess.channel == "winaprize" and sess.status == "playing"
            )

    # --- Online Friend Rooms (/game#XXXXXX) ---

    def _generate_room_code(self) -> str:
        for _ in range(30):
            code = secrets.token_hex(3).upper()
            if code not in self._rooms:
                return code
        return secrets.token_hex(4).upper()

    def get_room(self, room_code: str) -> GameSession:
        code = room_code.strip().upper().lstrip("#")
        with self._lock:
            sid = self._rooms.get(code)
            if sid is None or sid not in self._sessions:
                raise GameError(f"Salon #{code} introuvable ou expiré.", status_code=404)
            session = self._sessions[sid]
            session.updated_at = time.time()
            return session

    def create_room(
        self,
        username: str,
        rows: int = 6,
        cols: int = 7,
        align: int = 4,
        starting_player: Any = 1,
        random_start: bool = False,
    ) -> tuple[GameStateResponse, str, int]:
        starter, was_random = _resolve_starting_player(starting_player, random_start)
        config = GameConfig(
            rows=rows,
            cols=cols,
            align=align,
            mode="player_vs_player",
            starting_player=starter,
            random_start=was_random,
            username=username,
            player2_name="En attente d'un ami…",
        )
        session_id = str(uuid.uuid4())
        p1_token = secrets.token_urlsafe(24)

        with self._lock:
            self._evict_stale()
            code = self._generate_room_code()
            session = _build_session(
                session_id,
                config,
                channel="online_pvp",
                room_code=code,
                waiting_for_opponent=True,
                allow_undo=False,
                player_tokens={1: p1_token},
                on_change=self._on_session_change,
                on_finish=self._on_session_finish,
            )
            self._sessions[session_id] = session
            self._rooms[code] = session_id

        self._on_session_change(session)
        with session.lock:
            return session.to_response(), p1_token, 1

    def join_room(
        self, room_code: str, username: str
    ) -> tuple[GameStateResponse, Optional[str], int]:
        session = self.get_room(room_code)
        cleaned = (username or "Invité").strip()[:32] or "Invité"

        with session.lock:
            if session.waiting_for_opponent and 2 not in session.player_tokens:
                p2_token = secrets.token_urlsafe(24)
                p2_display = (
                    cleaned
                    if cleaned != session.player_meta[1].name
                    else f"{cleaned} (J2)"
                )
                session.player_tokens[2] = p2_token
                session.config.player2_name = p2_display
                session.player_objs[2].name = p2_display
                session.player_meta[2].name = p2_display
                session.c4.players[2][0] = p2_display
                session.waiting_for_opponent = False
                session.updated_at = time.time()
                resp = session.to_response()
                seat = 2
                token_out: Optional[str] = p2_token
            else:
                resp = session.to_response()
                seat = 0
                token_out = None

        if seat == 2:
            self._on_session_change(session)
        return resp, token_out, seat

    def play_room_move(
        self, room_code: str, col: int, player_token: str
    ) -> GameStateResponse:
        session = self.get_room(room_code)
        with session.lock:
            if session.waiting_for_opponent:
                raise GameError("En attente que votre ami rejoigne la partie.", status_code=409)
            expected_token = session.player_tokens.get(session.c4.current_player)
            if not expected_token or not secrets.compare_digest(player_token, expected_token):
                raise GameError("Ce n'est pas votre tour (ou vous êtes spectateur).", status_code=403)
        applied = session.play_human_move(col=col, auto_ai_reply=False)
        with session.lock:
            return session.to_response(moves_applied=applied)

    def rematch_room(
        self, room_code: str, player_token: str, random_start: bool = False
    ) -> GameStateResponse:
        session = self.get_room(room_code)
        with session.lock:
            valid_tokens = list(session.player_tokens.values())
            if not any(secrets.compare_digest(player_token, tok) for tok in valid_tokens):
                raise GameError("Seuls les joueurs du salon peuvent lancer une revanche.", status_code=403)
            if session.waiting_for_opponent:
                raise GameError("En attente que votre ami rejoigne d'abord.", status_code=409)

            next_starter = (
                random.choice([1, 2])
                if random_start
                else (2 if session.config.starting_player == 1 else 1)
            )
            session.config.starting_player = next_starter
            session.config.random_start = random_start
            session.c4.grid = [
                [0 for _ in range(session.c4.col)] for _ in range(session.c4.row)
            ]
            session.c4.current_player = next_starter
            session.status = "playing"
            session.winner = None
            session.winning_cells = []
            session.move_history = []
            session.snapshots = []
            session.last_ai_info = None
            session.persisted = False
            session.created_at = time.time()
            session.updated_at = time.time()
            resp = session.to_response()

        self._on_session_change(session)
        return resp
