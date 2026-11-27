import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Optional

from blacklist_defaults import DEFAULT_BLACKLIST_ENTRIES

DEFAULT_WINAPRIZE_CONFIG: dict[str, Any] = {
    "enabled": True,
    "rows": 6,
    "cols": 7,
    "align": 4,
    "ai_level": "medium",
    "starting_player": 1,
    "human_player": 1,
    "random_start": False,
    "allow_undo": False,
    "title": "Défi Puissance 4",
    "subtitle": "Battez l'IA pour gagner un prix !",
}

_LEET_TRANS = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
        "!": "i",
    }
)


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_username(name: str) -> str:
    folded = _strip_accents((name or "").strip().lower())
    return " ".join(folded.split())


def _compact_leet(text: str) -> str:
    folded = _strip_accents((text or "").strip().lower()).translate(_LEET_TRANS)
    return re.sub(r"[^a-z0-9]", "", folded)


def _tokenize_words(text: str) -> set[str]:
    folded = _strip_accents((text or "").strip().lower())
    tokens = set(re.findall(r"[a-z0-9]+", folded))
    leet_tokens = set(re.findall(r"[a-z0-9]+", folded.translate(_LEET_TRANS)))
    return tokens | leet_tokens


class Database:
    """Thread-safe SQLite (WAL mode) persistence layer for games, settings, and blacklist."""

    def __init__(self, db_path: Optional[str] = None, seed_blacklist: bool = True):
        env_path = os.getenv("CONNECT4_DB_PATH")
        if db_path is not None:
            resolved = Path(db_path)
        elif env_path:
            resolved = Path(env_path)
        else:
            resolved = Path(__file__).resolve().parent.parent / "data" / "connect4.db"

        resolved.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(resolved)
        self._lock = threading.Lock()
        self._init_schema(seed_blacklist=seed_blacklist)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self, seed_blacklist: bool = True):
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS game_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'normal',
                    room_code TEXT,
                    mode TEXT NOT NULL,
                    username TEXT NOT NULL,
                    player2_name TEXT NOT NULL,
                    rows INTEGER NOT NULL,
                    cols INTEGER NOT NULL,
                    align INTEGER NOT NULL,
                    ai_level TEXT,
                    ai2_level TEXT,
                    starting_player INTEGER NOT NULL,
                    human_player INTEGER,
                    status TEXT NOT NULL,
                    end_reason TEXT NOT NULL DEFAULT 'win',
                    winner INTEGER,
                    winner_name TEXT,
                    human_outcome TEXT,
                    total_plies INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    final_grid_json TEXT NOT NULL,
                    move_history_json TEXT NOT NULL,
                    winning_cells_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    finished_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_game_records_channel_finished
                    ON game_records (channel, finished_at DESC);
                CREATE INDEX IF NOT EXISTS idx_game_records_username
                    ON game_records (username);
                CREATE INDEX IF NOT EXISTS idx_game_records_finished
                    ON game_records (finished_at DESC);

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS username_blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    match_type TEXT NOT NULL DEFAULT 'exact',
                    reason TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    UNIQUE(pattern, match_type)
                );
                """
            )

            # Safe schema migration for existing VPS databases created before end_reason
            cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(game_records)").fetchall()
            }
            if "end_reason" not in cols:
                conn.execute(
                    "ALTER TABLE game_records ADD COLUMN end_reason TEXT NOT NULL DEFAULT 'win'"
                )
                conn.execute(
                    "UPDATE game_records SET end_reason = CASE WHEN status = 'draw' THEN 'draw' ELSE 'win' END"
                )

            row = conn.execute(
                "SELECT key, value_json FROM app_settings WHERE key = 'winaprize_config'"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                    ("winaprize_config", json.dumps(DEFAULT_WINAPRIZE_CONFIG), time.time()),
                )
            else:
                # Auto-translate legacy English default title/subtitle stored on existing VPS DBs
                try:
                    stored_cfg = json.loads(row["value_json"])
                    legacy_titles = {
                        "connect 4 challenge",
                        "connect 4 prize challenge",
                        "win a prize",
                        "prize challenge",
                    }
                    legacy_subtitles = {
                        "beat the ai to win a prize!",
                        "beat the ai to win a prize",
                        "challenge the ai to win a prize!",
                    }
                    changed = False
                    if (stored_cfg.get("title") or "").strip().lower() in legacy_titles:
                        stored_cfg["title"] = DEFAULT_WINAPRIZE_CONFIG["title"]
                        changed = True
                    if (stored_cfg.get("subtitle") or "").strip().lower() in legacy_subtitles:
                        stored_cfg["subtitle"] = DEFAULT_WINAPRIZE_CONFIG["subtitle"]
                        changed = True
                    if changed:
                        conn.execute(
                            "UPDATE app_settings SET value_json = ?, updated_at = ? WHERE key = 'winaprize_config'",
                            (json.dumps(stored_cfg), time.time()),
                        )
                except Exception:
                    pass

            # Seed built-in moderation blacklist once automatically
            if seed_blacklist:
                seeded = conn.execute(
                    "SELECT key FROM app_settings WHERE key = 'blacklist_seeded_v1'"
                ).fetchone()
                if seeded is None:
                    now = time.time()
                    for pat, mtype, reason in DEFAULT_BLACKLIST_ENTRIES:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO username_blacklist (pattern, match_type, reason, created_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (normalize_username(pat), mtype, reason, now),
                        )
                    conn.execute(
                        "INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                        ("blacklist_seeded_v1", json.dumps({"seeded": True}), now),
                    )

    # --- Win a Prize Config ---

    def get_winaprize_config(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key = 'winaprize_config'"
            ).fetchone()
        if row is None:
            return dict(DEFAULT_WINAPRIZE_CONFIG)
        merged = dict(DEFAULT_WINAPRIZE_CONFIG)
        merged.update(json.loads(row["value_json"]))
        return merged

    def save_winaprize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = dict(DEFAULT_WINAPRIZE_CONFIG)
        merged.update(config)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value_json, updated_at)
                VALUES ('winaprize_config', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (json.dumps(merged), time.time()),
            )
        return merged

    # --- Username Blacklist ---

    def seed_default_blacklist(self) -> int:
        now = time.time()
        added = 0
        with self._lock, self._connect() as conn:
            for pat, mtype, reason in DEFAULT_BLACKLIST_ENTRIES:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO username_blacklist (pattern, match_type, reason, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (normalize_username(pat), mtype, reason, now),
                )
                added += cur.rowcount
        return added

    def list_blacklist(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, pattern, match_type, reason, created_at FROM username_blacklist ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_blacklist_entry(
        self, pattern: str, match_type: str = "exact", reason: str = ""
    ) -> dict[str, Any]:
        norm = normalize_username(pattern)
        if not norm:
            raise ValueError("Le motif de liste noire ne peut pas être vide.")
        if match_type not in ("exact", "contains"):
            raise ValueError("match_type doit être 'exact' ou 'contains'.")
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO username_blacklist (pattern, match_type, reason, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pattern, match_type) DO UPDATE SET
                    reason = excluded.reason,
                    created_at = excluded.created_at
                """,
                (norm, match_type, reason.strip()[:120], now),
            )
            row = conn.execute(
                "SELECT id, pattern, match_type, reason, created_at FROM username_blacklist WHERE pattern = ? AND match_type = ?",
                (norm, match_type),
            ).fetchone()
        return dict(row)

    def delete_blacklist_entry(self, entry_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM username_blacklist WHERE id = ?", (entry_id,))
        return cur.rowcount > 0

    def is_username_blocked(self, username: str) -> tuple[bool, Optional[str]]:
        norm = normalize_username(username)
        if not norm:
            return False, None
        compact = _compact_leet(username)
        words = _tokenize_words(username)

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT pattern, match_type, reason FROM username_blacklist"
            ).fetchall()

        for row in rows:
            pat = row["pattern"]
            mtype = row["match_type"]
            pat_compact = _compact_leet(pat)
            if mtype == "exact":
                if norm == pat or compact == pat_compact or pat in words:
                    return True, row["reason"] or None
            elif mtype == "contains":
                if pat in norm or (len(pat_compact) >= 4 and pat_compact in compact):
                    return True, row["reason"] or None
        return False, None

    # --- Finished Game Records ---

    def save_finished_game(self, snapshot: dict[str, Any]) -> int:
        cfg = snapshot["config"]
        players = snapshot["players"]
        channel = snapshot.get("channel", "normal")
        mode = cfg["mode"]
        status = snapshot["status"]
        end_reason = snapshot.get("end_reason") or (
            "draw" if status == "draw" else "win"
        )
        winner = snapshot.get("winner")
        winner_name = (
            players[str(winner)]["name"]
            if winner is not None and str(winner) in players
            else None
        )

        human_outcome: Optional[str] = None
        if status == "forfeit":
            if end_reason == "accidental_exit":
                human_outcome = "forfeit_exit"
            elif end_reason == "abandon_restart":
                human_outcome = "forfeit_abandon"
            else:
                human_outcome = "forfeit_manual"
        elif mode == "human_vs_ai":
            if status == "draw":
                human_outcome = "draw"
            elif winner == cfg["human_player"]:
                human_outcome = "win"
            else:
                human_outcome = "loss"
        elif status == "draw":
            human_outcome = "draw"

        created_at = float(snapshot.get("created_at", time.time()))
        finished_at = float(snapshot.get("updated_at", time.time()))
        duration = round(max(0.0, finished_at - created_at), 2)

        p1_name = players.get("1", {}).get("name", snapshot.get("username", "Invité"))
        p2_name = players.get("2", {}).get("name", cfg.get("player2_name", "Joueur 2"))

        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO game_records (
                    session_id, channel, room_code, mode, username, player2_name,
                    rows, cols, align, ai_level, ai2_level, starting_player,
                    human_player, status, end_reason, winner, winner_name, human_outcome,
                    total_plies, duration_seconds, final_grid_json,
                    move_history_json, winning_cells_json, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["session_id"],
                    channel,
                    snapshot.get("room_code"),
                    mode,
                    snapshot.get("username", p1_name),
                    p2_name,
                    int(cfg["rows"]),
                    int(cfg["cols"]),
                    int(cfg["align"]),
                    cfg.get("ai_level") if mode != "player_vs_player" else None,
                    cfg.get("ai2_level") if mode == "ai_vs_ai" else None,
                    int(cfg["starting_player"]),
                    int(cfg["human_player"]) if mode == "human_vs_ai" else None,
                    status,
                    end_reason,
                    winner,
                    winner_name,
                    human_outcome,
                    len(snapshot.get("move_history", [])),
                    duration,
                    json.dumps(snapshot.get("grid", [])),
                    json.dumps(snapshot.get("move_history", [])),
                    json.dumps(snapshot.get("winning_cells", [])),
                    created_at,
                    finished_at,
                ),
            )
            return int(cur.lastrowid)

    def list_game_records(
        self,
        channel: Optional[str] = None,
        outcome: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses = []
        params: list[Any] = []

        if channel and channel != "all":
            clauses.append("channel = ?")
            params.append(channel)
        if outcome and outcome != "all":
            if outcome in (
                "win",
                "loss",
                "draw",
                "forfeit_abandon",
                "forfeit_exit",
                "forfeit_manual",
            ):
                clauses.append("human_outcome = ?")
                params.append(outcome)
            elif outcome == "forfeit_any":
                clauses.append("status = 'forfeit'")
        if search and search.strip():
            like = f"%{search.strip().lower()}%"
            clauses.append(
                "(LOWER(username) LIKE ? OR LOWER(player2_name) LIKE ? OR LOWER(COALESCE(room_code, '')) LIKE ? OR LOWER(session_id) LIKE ?)"
            )
            params.extend([like, like, like, like])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        with self._lock, self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM game_records {where_sql}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"""
                SELECT id, session_id, channel, room_code, mode, username, player2_name,
                       rows, cols, align, ai_level, ai2_level, starting_player,
                       human_player, status, end_reason, winner, winner_name, human_outcome,
                       total_plies, duration_seconds, created_at, finished_at
                FROM game_records
                {where_sql}
                ORDER BY finished_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return {"total": int(total), "records": [dict(r) for r in rows]}

    def get_game_record(self, record_id: int) -> Optional[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM game_records WHERE id = ?", (record_id,)
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["final_grid"] = json.loads(data.pop("final_grid_json"))
        data["move_history"] = json.loads(data.pop("move_history_json"))
        data["winning_cells"] = json.loads(data.pop("winning_cells_json"))
        return data

    def delete_game_record(self, record_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM game_records WHERE id = ?", (record_id,))
        return cur.rowcount > 0

    def get_stats(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            overall_row = conn.execute(
                """
                SELECT COUNT(*) AS total_games,
                       COUNT(DISTINCT LOWER(username)) AS unique_players,
                       COALESCE(AVG(total_plies), 0) AS avg_plies,
                       COALESCE(AVG(duration_seconds), 0) AS avg_duration_s,
                       SUM(CASE WHEN human_outcome = 'forfeit_abandon' THEN 1 ELSE 0 END) AS forfeit_abandon,
                       SUM(CASE WHEN human_outcome = 'forfeit_exit' THEN 1 ELSE 0 END) AS forfeit_exit,
                       SUM(CASE WHEN human_outcome = 'forfeit_manual' THEN 1 ELSE 0 END) AS forfeit_manual
                FROM game_records
                """
            ).fetchone()

            def _channel_human_ai_stats(channel_name: str) -> dict[str, Any]:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS total_games,
                           SUM(CASE WHEN human_outcome = 'win' THEN 1 ELSE 0 END) AS human_wins,
                           SUM(CASE WHEN human_outcome = 'loss' THEN 1 ELSE 0 END) AS ai_wins,
                           SUM(CASE WHEN human_outcome = 'draw' THEN 1 ELSE 0 END) AS draws,
                           SUM(CASE WHEN human_outcome = 'forfeit_abandon' THEN 1 ELSE 0 END) AS forfeit_abandon,
                           SUM(CASE WHEN human_outcome = 'forfeit_exit' THEN 1 ELSE 0 END) AS forfeit_exit,
                           SUM(CASE WHEN human_outcome = 'forfeit_manual' THEN 1 ELSE 0 END) AS forfeit_manual,
                           COUNT(DISTINCT LOWER(username)) AS unique_players,
                           COALESCE(AVG(total_plies), 0) AS avg_plies
                    FROM game_records
                    WHERE channel = ? AND mode = 'human_vs_ai'
                    """,
                    (channel_name,),
                ).fetchone()
                total = int(row["total_games"] or 0)
                hwins = int(row["human_wins"] or 0)
                aiwins = int(row["ai_wins"] or 0)
                draws = int(row["draws"] or 0)

                lvl_rows = conn.execute(
                    """
                    SELECT COALESCE(ai_level, 'medium') AS level,
                           COUNT(*) AS total,
                           SUM(CASE WHEN human_outcome = 'win' THEN 1 ELSE 0 END) AS human_wins,
                           SUM(CASE WHEN human_outcome = 'loss' THEN 1 ELSE 0 END) AS ai_wins,
                           SUM(CASE WHEN human_outcome = 'draw' THEN 1 ELSE 0 END) AS draws,
                           SUM(CASE WHEN status = 'forfeit' THEN 1 ELSE 0 END) AS forfeits
                    FROM game_records
                    WHERE channel = ? AND mode = 'human_vs_ai'
                    GROUP BY COALESCE(ai_level, 'medium')
                    """,
                    (channel_name,),
                ).fetchall()

                level_order = {"easy": 0, "medium": 1, "hard": 2, "impossible": 3}
                by_level = []
                for lr in sorted(lvl_rows, key=lambda r: level_order.get(r["level"], 99)):
                    lt = int(lr["total"] or 0)
                    lh = int(lr["human_wins"] or 0)
                    by_level.append(
                        {
                            "level": lr["level"],
                            "total": lt,
                            "human_wins": lh,
                            "ai_wins": int(lr["ai_wins"] or 0),
                            "draws": int(lr["draws"] or 0),
                            "forfeits": int(lr["forfeits"] or 0),
                            "win_rate_pct": round((lh / lt) * 100, 1) if lt else 0.0,
                        }
                    )

                return {
                    "total_games": total,
                    "human_wins": hwins,
                    "ai_wins": aiwins,
                    "draws": draws,
                    "forfeit_abandon": int(row["forfeit_abandon"] or 0),
                    "forfeit_exit": int(row["forfeit_exit"] or 0),
                    "forfeit_manual": int(row["forfeit_manual"] or 0),
                    "win_rate_pct": round((hwins / total) * 100, 1) if total else 0.0,
                    "unique_players": int(row["unique_players"] or 0),
                    "avg_plies": round(float(row["avg_plies"] or 0), 1),
                    "by_level": by_level,
                }

            prize_stats = _channel_human_ai_stats("winaprize")
            prize_winners_rows = conn.execute(
                """
                SELECT id, session_id, username, ai_level, rows, cols, align,
                       total_plies, duration_seconds, finished_at
                FROM game_records
                WHERE channel = 'winaprize' AND human_outcome = 'win'
                ORDER BY finished_at DESC
                LIMIT 30
                """
            ).fetchall()
            prize_stats["recent_winners"] = [dict(r) for r in prize_winners_rows]

            normal_stats = _channel_human_ai_stats("normal")
            normal_extra = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN mode = 'player_vs_player' THEN 1 ELSE 0 END) AS local_pvp_total,
                    SUM(CASE WHEN mode = 'ai_vs_ai' THEN 1 ELSE 0 END) AS ai_vs_ai_total
                FROM game_records
                WHERE channel = 'normal'
                """
            ).fetchone()
            normal_stats["local_pvp_total"] = int(normal_extra["local_pvp_total"] or 0)
            normal_stats["ai_vs_ai_total"] = int(normal_extra["ai_vs_ai_total"] or 0)

            online_row = conn.execute(
                """
                SELECT COUNT(*) AS total_games,
                       SUM(CASE WHEN status = 'win' THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN status = 'draw' THEN 1 ELSE 0 END) AS draws,
                       COALESCE(AVG(total_plies), 0) AS avg_plies
                FROM game_records
                WHERE channel = 'online_pvp'
                """
            ).fetchone()
            online_stats = {
                "total_games": int(online_row["total_games"] or 0),
                "wins": int(online_row["wins"] or 0),
                "draws": int(online_row["draws"] or 0),
                "avg_plies": round(float(online_row["avg_plies"] or 0), 1),
            }

            top_rows = conn.execute(
                """
                SELECT username,
                       COUNT(*) AS games_played,
                       SUM(CASE WHEN human_outcome = 'win' THEN 1 ELSE 0 END) AS ai_wins_beaten,
                       SUM(CASE WHEN channel = 'winaprize' AND human_outcome = 'win' THEN 1 ELSE 0 END) AS prize_wins
                FROM game_records
                WHERE mode = 'human_vs_ai'
                GROUP BY LOWER(username)
                ORDER BY prize_wins DESC, ai_wins_beaten DESC, games_played DESC
                LIMIT 15
                """
            ).fetchall()

        return {
            "overall": {
                "total_games": int(overall_row["total_games"] or 0),
                "unique_players": int(overall_row["unique_players"] or 0),
                "avg_plies": round(float(overall_row["avg_plies"] or 0), 1),
                "avg_duration_s": round(float(overall_row["avg_duration_s"] or 0), 1),
                "forfeit_abandon": int(overall_row["forfeit_abandon"] or 0),
                "forfeit_exit": int(overall_row["forfeit_exit"] or 0),
                "forfeit_manual": int(overall_row["forfeit_manual"] or 0),
            },
            "winaprize": prize_stats,
            "normal": normal_stats,
            "online_pvp": online_stats,
            "top_players": [dict(r) for r in top_rows],
        }
