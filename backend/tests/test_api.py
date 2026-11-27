import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["CONNECT4_DB_PATH"] = _tmp_db.name
os.environ["ADMIN_PASSWORD"] = "test-secret-admin"

from main import app

client = TestClient(app)


def _admin_headers():
    login = client.post("/api/admin/login", json={"password": "test-secret-admin"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']}"}


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_human_vs_ai_levels_username_and_undo():
    create_res = client.post(
        "/api/games",
        json={
            "rows": 6,
            "cols": 7,
            "align": 4,
            "mode": "human_vs_ai",
            "starting_player": 1,
            "human_player": 1,
            "ai_level": "hard",
            "username": "Ayoube",
        },
    )
    assert create_res.status_code == 201
    state = create_res.json()
    sid = state["session_id"]
    assert state["username"] == "Ayoube"
    assert state["config"]["ai_level"] == "hard"
    assert state["players"]["1"]["name"] == "Ayoube"
    assert state["players"]["2"]["level"] == "hard"

    move_res = client.post(f"/api/games/{sid}/move", json={"col": 3})
    assert move_res.status_code == 200
    state = move_res.json()
    assert len(state["moves_applied"]) == 2
    assert state["moves_applied"][1]["ai_info"]["level"] == "hard"
    assert state["moves_applied"][1]["ai_info"]["strategy"] == "minimax"

    undo_res = client.post(f"/api/games/{sid}/undo")
    assert undo_res.status_code == 200
    assert undo_res.json()["move_history"] == []


def test_player_vs_player_and_random_start():
    create_res = client.post(
        "/api/games",
        json={
            "mode": "player_vs_player",
            "username": "Alice",
            "player2_name": "Bob",
            "starting_player": "random",
        },
    )
    assert create_res.status_code == 201
    state = create_res.json()
    sid = state["session_id"]
    assert state["config"]["random_start"] is True
    assert state["current_player"] in (1, 2)

    first_player = state["current_player"]
    m1 = client.post(f"/api/games/{sid}/move", json={"col": 2}).json()
    assert len(m1["moves_applied"]) == 1
    assert m1["moves_applied"][0]["player"] == first_player

    m2 = client.post(f"/api/games/{sid}/move", json={"col": 3}).json()
    assert len(m2["move_history"]) == 2

    u1 = client.post(f"/api/games/{sid}/undo").json()
    assert len(u1["move_history"]) == 1


def test_live_mid_game_difficulty_switching_and_winaprize():
    headers = _admin_headers()

    # Configure /winaprize to start on medium
    upd = client.put(
        "/api/admin/winaprize/config",
        headers=headers,
        json={
            "enabled": True,
            "rows": 6,
            "cols": 7,
            "align": 4,
            "ai_level": "medium",
            "starting_player": 1,
            "human_player": 1,
            "random_start": False,
            "allow_undo": False,
            "title": "Prize Challenge",
            "subtitle": "Beat AI!",
            "apply_to_live_games": True,
        },
    )
    assert upd.status_code == 200

    # Public config intentionally omits ai_level
    pub_cfg = client.get("/api/winaprize/config").json()
    assert pub_cfg["enabled"] is True
    assert "ai_level" not in pub_cfg

    # Player starts a /winaprize game
    g_res = client.post("/api/winaprize/games", json={"username": "PrizeHunter"})
    assert g_res.status_code == 201
    game = g_res.json()
    sid = game["session_id"]
    assert game["channel"] == "winaprize"
    assert game["allow_undo"] is False
    assert game["players"]["2"]["level"] is None  # Stealth on public response

    # Play move 1 -> AI plays medium (heuristic)
    m1 = client.post(f"/api/games/{sid}/move", json={"col": 3}).json()
    assert len(m1["move_history"]) == 2
    assert m1["ai_info"] is None  # Hidden from prize player

    # Admin switches /winaprize difficulty globally to impossible mid-game!
    upd2 = client.put(
        "/api/admin/winaprize/config",
        headers=headers,
        json={
            "enabled": True,
            "rows": 6,
            "cols": 7,
            "align": 4,
            "ai_level": "impossible",
            "starting_player": 1,
            "human_player": 1,
            "random_start": False,
            "allow_undo": False,
            "title": "Prize Challenge",
            "subtitle": "Beat AI!",
            "apply_to_live_games": True,
        },
    )
    assert upd2.status_code == 200
    assert upd2.json()["updated_live_games"] >= 1

    # Verify in Admin sessions that the live game immediately switched to impossible
    admin_list = client.get("/api/admin/sessions", headers=headers).json()["sessions"]
    live = next(s for s in admin_list if s["session_id"] == sid)
    assert live["config"]["ai_level"] == "impossible"

    # Next human move triggers AI at impossible (minimax) without resetting board!
    client.post(f"/api/games/{sid}/move", json={"col": 2})
    admin_list2 = client.get("/api/admin/sessions", headers=headers).json()["sessions"]
    live2 = next(s for s in admin_list2 if s["session_id"] == sid)
    assert len(live2["move_history"]) == 4
    assert live2["ai_info"]["level"] == "impossible"
    assert live2["ai_info"]["strategy"] == "minimax"

    # Also test per-session PATCH difficulty override
    patch_res = client.patch(
        f"/api/admin/sessions/{sid}/difficulty",
        headers=headers,
        json={"ai_level": "easy"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["config"]["ai_level"] == "easy"


def test_online_friend_room_and_persistence_stats():
    headers = _admin_headers()

    # Player 1 creates an online hex room
    create = client.post(
        "/api/rooms",
        json={"username": "HostUser", "rows": 4, "cols": 4, "align": 3},
    )
    assert create.status_code == 201
    room = create.json()
    code = room["room_code"]
    assert len(code) == 6
    int(code, 16)  # Valid hex
    assert room["seat"] == 1
    p1_token = room["player_token"]
    assert room["game"]["waiting_for_opponent"] is True

    # Cannot move before friend joins
    assert (
        client.post(f"/api/rooms/{code}/move", json={"col": 0, "player_token": p1_token}).status_code
        == 409
    )

    # Friend joins as Player 2
    join = client.post(f"/api/rooms/{code}/join", json={"username": "FriendUser"})
    assert join.status_code == 200
    assert join.json()["seat"] == 2
    p2_token = join.json()["player_token"]
    assert join.json()["game"]["waiting_for_opponent"] is False

    # 3rd visitor becomes spectator (seat 0)
    spec = client.post(f"/api/rooms/{code}/join", json={"username": "Watcher"})
    assert spec.status_code == 200
    assert spec.json()["seat"] == 0
    assert spec.json()["player_token"] is None

    # Wrong player cannot move on Player 1's turn
    assert (
        client.post(f"/api/rooms/{code}/move", json={"col": 0, "player_token": p2_token}).status_code
        == 403
    )

    # Play quick 3-in-a-row win for Player 1 (cols 0, 1, 2)
    client.post(f"/api/rooms/{code}/move", json={"col": 0, "player_token": p1_token})
    client.post(f"/api/rooms/{code}/move", json={"col": 0, "player_token": p2_token})
    client.post(f"/api/rooms/{code}/move", json={"col": 1, "player_token": p1_token})
    client.post(f"/api/rooms/{code}/move", json={"col": 1, "player_token": p2_token})
    win_res = client.post(f"/api/rooms/{code}/move", json={"col": 2, "player_token": p1_token})
    assert win_res.status_code == 200
    assert win_res.json()["status"] == "win"
    assert win_res.json()["winner"] == 1

    # Verify saved in persistent SQLite history & stats
    stats = client.get("/api/admin/stats", headers=headers).json()
    assert stats["online_pvp"]["total_games"] >= 1
    history = client.get("/api/admin/history?channel=online_pvp", headers=headers).json()
    assert history["total"] >= 1
    rec_id = history["records"][0]["id"]
    replay = client.get(f"/api/admin/history/{rec_id}", headers=headers).json()
    assert len(replay["move_history"]) == 5

    # Rematch works on same room code
    rematch = client.post(
        f"/api/rooms/{code}/rematch",
        json={"player_token": p2_token, "random_start": False},
    )
    assert rematch.status_code == 200
    assert rematch.json()["status"] == "playing"
    assert rematch.json()["move_history"] == []


def test_username_blacklist_enforcement():
    headers = _admin_headers()

    e1 = client.post(
        "/api/admin/blacklist",
        headers=headers,
        json={"pattern": "TrollKing", "match_type": "exact", "reason": "Spam"},
    )
    assert e1.status_code == 201
    entry_id = e1.json()["id"]

    e2 = client.post(
        "/api/admin/blacklist",
        headers=headers,
        json={"pattern": "badword", "match_type": "contains", "reason": "Profanity"},
    )
    assert e2.status_code == 201
    entry2_id = e2.json()["id"]

    # Blocked across normal, winaprize, and online rooms (case-insensitive)
    assert client.post("/api/games", json={"username": "  trollking  "}).status_code == 403
    assert client.post("/api/winaprize/games", json={"username": "MyBadWord99"}).status_code == 403
    assert client.post("/api/rooms", json={"username": "BADWORD"}).status_code == 403

    # Removing entry restores access
    assert client.delete(f"/api/admin/blacklist/{entry_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/admin/blacklist/{entry2_id}", headers=headers).status_code == 204
    assert client.post("/api/games", json={"username": "TrollKing"}).status_code == 201


def test_admin_auth_and_logout():
    assert client.get("/api/admin/sessions").status_code == 401
    assert client.get("/api/admin/stats").status_code == 401
    assert client.post("/api/admin/login", json={"password": "wrong"}).status_code == 401

    headers = _admin_headers()
    assert client.post("/api/admin/logout", headers=headers).status_code == 204
    assert client.get("/api/admin/sessions", headers=headers).status_code == 401
