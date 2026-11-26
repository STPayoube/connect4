import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["ADMIN_PASSWORD"] = "test-secret-admin"

from main import app

client = TestClient(app)


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
    assert state["config"]["ai_depth"] == 3
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
    assert state["players"]["1"]["type"] == "human"
    assert state["players"]["2"]["type"] == "human"
    assert state["players"]["1"]["name"] == "Alice"
    assert state["players"]["2"]["name"] == "Bob"

    first_player = state["current_player"]
    m1 = client.post(f"/api/games/{sid}/move", json={"col": 2}).json()
    assert len(m1["moves_applied"]) == 1
    assert m1["moves_applied"][0]["player"] == first_player
    assert m1["current_player"] == (2 if first_player == 1 else 1)

    m2 = client.post(f"/api/games/{sid}/move", json={"col": 3}).json()
    assert len(m2["move_history"]) == 2

    # In PvP, undo rewinds 1 ply
    u1 = client.post(f"/api/games/{sid}/undo").json()
    assert len(u1["move_history"]) == 1


def test_admin_auth_and_multi_session_monitoring():
    # Unauthenticated access rejected
    assert client.get("/api/admin/sessions").status_code == 401
    assert client.post("/api/admin/login", json={"password": "wrong"}).status_code == 401

    login = client.post("/api/admin/login", json={"password": "test-secret-admin"})
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Two different users start games simultaneously
    s_u1 = client.post("/api/games", json={"username": "UserAlpha", "ai_level": "easy"}).json()["session_id"]
    s_u2 = client.post("/api/games", json={"username": "UserBeta", "mode": "player_vs_player"}).json()["session_id"]
    client.post(f"/api/games/{s_u1}/move", json={"col": 3, "auto_ai_reply": False})

    listing = client.get("/api/admin/sessions", headers=headers)
    assert listing.status_code == 200
    sessions_by_id = {s["session_id"]: s for s in listing.json()["sessions"]}
    assert s_u1 in sessions_by_id
    assert s_u2 in sessions_by_id
    assert sessions_by_id[s_u1]["username"] == "UserAlpha"
    assert len(sessions_by_id[s_u1]["move_history"]) == 1
    assert sessions_by_id[s_u2]["username"] == "UserBeta"

    # Admin can delete a session
    assert client.delete(f"/api/admin/sessions/{s_u2}", headers=headers).status_code == 204
    assert client.get(f"/api/games/{s_u2}").status_code == 404

    # Logout invalidates token
    assert client.post("/api/admin/logout", headers=headers).status_code == 204
    assert client.get("/api/admin/sessions", headers=headers).status_code == 401


def test_ai_vs_ai_levels_and_validation():
    res = client.post(
        "/api/games",
        json={
            "rows": 4,
            "cols": 4,
            "align": 3,
            "mode": "ai_vs_ai",
            "ai_level": "medium",
            "ai2_level": "impossible",
        },
    )
    assert res.status_code == 201
    sid = res.json()["session_id"]
    step1 = client.post(f"/api/games/{sid}/ai-move")
    assert step1.status_code == 200
    step2 = client.post(f"/api/games/{sid}/ai-move")
    assert step2.status_code == 200
    assert step2.json()["ai_info"]["level"] == "impossible"

    assert client.post("/api/games", json={"rows": 4, "cols": 5, "align": 5}).status_code == 422
    assert client.get("/api/games/does-not-exist").status_code == 404
