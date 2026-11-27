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


def test_live_board_resize_and_collision_error():
    headers = _admin_headers()

    # Start a /winaprize game on 6x7
    client.put(
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
            "title": "Défi",
            "subtitle": "Gagnez !",
            "apply_to_live_games": False,
        },
    )
    game = client.post("/api/winaprize/games", json={"username": "ResizePlayer"}).json()
    sid = game["session_id"]

    # Place a checker in column index 6 (7th column)
    client.post(f"/api/games/{sid}/move", json={"col": 6, "auto_ai_reply": False})

    # Shrinking to 6 columns via live-config must fail with 409 collision!
    conflict = client.patch(
        f"/api/admin/sessions/{sid}/live-config",
        headers=headers,
        json={"cols": 6},
    )
    assert conflict.status_code == 409
    assert "colonne" in conflict.json()["detail"].lower()

    # Shrinking via /winaprize global PUT with apply_to_live_games=True must also fail with 409
    global_conflict = client.put(
        "/api/admin/winaprize/config",
        headers=headers,
        json={
            "enabled": True,
            "rows": 6,
            "cols": 5,
            "align": 4,
            "ai_level": "hard",
            "starting_player": 1,
            "human_player": 1,
            "random_start": False,
            "allow_undo": False,
            "title": "Défi",
            "subtitle": "Gagnez !",
            "apply_to_live_games": True,
        },
    )
    assert global_conflict.status_code == 409

    # Growing to 8x9 must succeed and preserve the checker on the bottom row (row 7, col 6)
    grown = client.patch(
        f"/api/admin/sessions/{sid}/live-config",
        headers=headers,
        json={"rows": 8, "cols": 9, "align": 4, "ai_level": "hard"},
    )
    assert grown.status_code == 200
    g_data = grown.json()
    assert len(g_data["grid"]) == 8
    assert len(g_data["grid"][0]) == 9
    assert g_data["grid"][7][6] == 1
    assert g_data["config"]["ai_level"] == "hard"

    # Clean up session so subsequent tests stay isolated
    client.delete(f"/api/admin/sessions/{sid}", headers=headers)


def test_websockets_game_room_and_admin():
    headers = _admin_headers()

    # 1. Live AI Game WebSocket receives live admin board resize & processes human+AI moves
    g = client.post("/api/games", json={"username": "WsPlayer", "ai_level": "easy"}).json()
    sid = g["session_id"]

    with client.websocket_connect(f"/api/ws/games/{sid}") as ws:
        init_msg = ws.receive_json()
        assert init_msg["event"] == "init"
        assert init_msg["data"]["session_id"] == sid

        # Admin resizes live over HTTP -> player receives instant WebSocket push
        client.patch(
            f"/api/admin/sessions/{sid}/live-config",
            headers=headers,
            json={"rows": 7, "cols": 8, "ai_level": "hard"},
        )
        upd_msg = ws.receive_json()
        assert upd_msg["event"] == "game_update"
        assert upd_msg["data"]["config"]["rows"] == 7
        assert upd_msg["data"]["config"]["cols"] == 8

        # Play a move directly over WebSocket (triggers human move + AI reply)
        ws.send_json({"type": "human_move", "col": 3, "auto_ai_reply": True})
        seen_plies = 0
        for _ in range(6):
            msg = ws.receive_json()
            if msg["event"] == "game_update":
                seen_plies = len(msg["data"]["move_history"])
                if seen_plies >= 2:
                    break
        assert seen_plies == 2

    # 2. Online Friend Room WebSocket
    room = client.post("/api/rooms", json={"username": "WsHost"}).json()
    code = room["room_code"]
    p1_tok = room["player_token"]
    p2_join = client.post(f"/api/rooms/{code}/join", json={"username": "WsFriend"}).json()
    assert p2_join["seat"] == 2

    with client.websocket_connect(f"/api/ws/rooms/{code}") as rws:
        r_init = rws.receive_json()
        assert r_init["event"] == "init"
        rws.send_json({"type": "move", "col": 2, "player_token": p1_tok})
        r_upd = rws.receive_json()
        assert r_upd["event"] == "room_update"
        assert len(r_upd["data"]["move_history"]) == 1


def test_reset_difficulty_mid_game_without_starting_player_no_500():
    """Regression test: changing ai_level via POST /reset with starting_player omitted (None)."""
    create = client.post(
        "/api/games",
        json={"username": "ResetTester", "ai_level": "medium", "mode": "human_vs_ai"},
    )
    assert create.status_code == 201
    sid = create.json()["session_id"]

    # Play one move first
    mv = client.post(f"/api/games/{sid}/move", json={"col": 3})
    assert mv.status_code == 200

    # Reset changing only ai_level (mirrors frontend handleQuickLevel payload)
    rst = client.post(
        f"/api/games/{sid}/reset",
        json={"ai_level": "hard", "ai2_level": "hard", "username": "ResetTester"},
    )
    assert rst.status_code == 200
    data = rst.json()
    assert data["status"] == "playing"
    assert data["config"]["ai_level"] == "hard"
    assert data["move_history"] == []


def test_default_blacklist_and_username_check_endpoint():
    headers = _admin_headers()

    # Built-in default blacklist should already block slurs, profanity, leetspeak, accents, admin
    assert client.post("/api/username/check", json={"username": "Ayoube"}).status_code == 200
    assert client.post("/api/username/check", json={"username": "Rapide"}).status_code == 200
    assert client.post("/api/username/check", json={"username": "admin"}).status_code == 403
    assert client.post("/api/username/check", json={"username": "f.u.c.k"}).status_code == 403
    assert client.post("/api/username/check", json={"username": "p0rnStar"}).status_code == 403
    assert client.post("/api/username/check", json={"username": "Connárd99"}).status_code == 403

    # Seed defaults endpoint should be idempotent
    seed = client.post("/api/admin/blacklist/seed-defaults", headers=headers)
    assert seed.status_code == 200
    assert seed.json()["added"] == 0
    assert len(seed.json()["entries"]) >= 70


def test_forfeit_reasons_and_distinct_stats():
    headers = _admin_headers()

    # 1. Manual end ("Fin de partie")
    g1 = client.post("/api/games", json={"username": "ForfeitUser1", "ai_level": "easy"}).json()
    client.post(f"/api/games/{g1['session_id']}/move", json={"col": 3})
    f1 = client.post(f"/api/games/{g1['session_id']}/forfeit", json={"reason": "manual_end"})
    assert f1.status_code == 200
    assert f1.json()["status"] == "forfeit"
    assert f1.json()["end_reason"] == "manual_end"

    # 2. Voluntary abandon / restart
    g2 = client.post("/api/games", json={"username": "ForfeitUser2", "ai_level": "easy"}).json()
    client.post(f"/api/games/{g2['session_id']}/move", json={"col": 2})
    f2 = client.post(f"/api/games/{g2['session_id']}/forfeit", json={"reason": "abandon_restart"})
    assert f2.status_code == 200
    assert f2.json()["status"] == "forfeit"
    assert f2.json()["end_reason"] == "abandon_restart"

    # 3. Accidental exit (user clicked "Non" on resume pop-up)
    g3 = client.post("/api/games", json={"username": "ForfeitUser3", "ai_level": "easy"}).json()
    client.post(f"/api/games/{g3['session_id']}/move", json={"col": 4})
    f3 = client.post(f"/api/games/{g3['session_id']}/forfeit", json={"reason": "accidental_exit"})
    assert f3.status_code == 200
    assert f3.json()["status"] == "forfeit"
    assert f3.json()["end_reason"] == "accidental_exit"

    # Verify stats distinguish all 3 forfeit types
    stats = client.get("/api/admin/stats", headers=headers).json()
    assert stats["normal"]["forfeit_manual"] >= 1
    assert stats["normal"]["forfeit_abandon"] >= 1
    assert stats["normal"]["forfeit_exit"] >= 1

    # Verify history outcome filtering works for each distinct forfeit type
    h_manual = client.get("/api/admin/history?outcome=forfeit_manual", headers=headers).json()
    assert any(r["username"] == "ForfeitUser1" for r in h_manual["records"])

    h_abandon = client.get("/api/admin/history?outcome=forfeit_abandon", headers=headers).json()
    assert any(r["username"] == "ForfeitUser2" for r in h_abandon["records"])

    h_exit = client.get("/api/admin/history?outcome=forfeit_exit", headers=headers).json()
    assert any(r["username"] == "ForfeitUser3" for r in h_exit["records"])


