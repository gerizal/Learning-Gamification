"""Teacher-owned quizzes (/api/live/quizzes) — edit key, duplicate, CRUD, delete vs archive, reorder, concurrency.

Needs db/010_teacher_quiz.sql applied (skips otherwise). Rows created here are deleted by primary key at the end
(packs we created, the questions inside them, games we created).
"""
from __future__ import annotations

import os
import socket
import threading
import time

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost:55432/playclass")
psycopg = pytest.importorskip("psycopg")
httpx = pytest.importorskip("httpx")


def _ready() -> str | None:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as c:
            n = c.execute("""SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'question_pack'
                              AND column_name IN ('edit_key_hash', 'owner_label')""").fetchone()[0]
        return None if n == 2 else "db/010_teacher_quiz.sql not applied (run scripts/dev_db.sh)"
    except Exception as exc:  # noqa: BLE001
        return f"DATABASE_URL unreachable: {exc.__class__.__name__}"


_reason = _ready()
if _reason:
    pytest.skip(_reason, allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import quiz  # noqa: E402
from app.main import app  # noqa: E402

TAG = "[pytest-quiz]"
PACKS: set[int] = set()
GAMES: set[str] = set()


def _cleanup():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        g = list(GAMES)
        if g:
            c.execute("DELETE FROM live_answer WHERE game_id = ANY(%s::uuid[])", (g,))
            c.execute("DELETE FROM live_player WHERE game_id = ANY(%s::uuid[])", (g,))
            c.execute("DELETE FROM live_question WHERE game_id = ANY(%s::uuid[])", (g,))
            c.execute("DELETE FROM live_game WHERE id = ANY(%s::uuid[])", (g,))
        qids = [r[0] for r in c.execute("SELECT id FROM question WHERE pack_id = ANY(%s)", (list(PACKS),))]
        c.execute("DELETE FROM question WHERE id = ANY(%s)", (qids,))
        c.execute("DELETE FROM question_pack WHERE id = ANY(%s)", (list(PACKS),))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    _cleanup()


@pytest.fixture(autouse=True)
def _limits():
    quiz.create_limiter.clear()
    yield
    quiz.create_limiter.clear()


@pytest.fixture(scope="module")
def server():
    import uvicorn

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off",
                                        loop="asyncio", timeout_graceful_shutdown=2))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(10)


def new_quiz(client, name=f"{TAG} My quiz", **extra):
    r = client.post("/api/live/quizzes", json={"name": name, **extra})
    assert r.status_code == 201, r.text
    body = r.json()
    PACKS.add(body["pack_id"])
    assert len(body["edit_key"]) >= 43
    body["K"] = {"X-Edit-Key": body["edit_key"]}
    return body


def add_q(client, qz, prompt="What is AI?", options=("Smart software", "A fruit"), correct=0, **extra):
    r = client.post(f"/api/live/quizzes/{qz['pack_id']}/questions", headers=qz["K"],
                    json={"prompt": f"{TAG} {prompt}", "options": list(options), "correct_option": correct, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _seeded_pack_id(client):
    for p in client.get("/api/live/packs").json():
        if not p["editable"] and p["question_counts"]["multiple_choice"] > 0:
            return p
    pytest.skip("no seeded pack with multiple_choice questions")


# ------------------------------------------------------------------ keys
def test_create_and_key_required(client):
    qz = new_quiz(client, description=" About AI ", owner_label="Cikgu Ana")
    pid = qz["pack_id"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        stored = c.execute("SELECT edit_key_hash, topic FROM question_pack WHERE id = %s", (pid,)).fetchone()
    assert stored[0] == quiz.hash_key(qz["edit_key"]) and qz["edit_key"] not in stored[0] and stored[1] == "general"
    got = client.get(f"/api/live/quizzes/{pid}", headers=qz["K"]).json()
    assert got["name"] == f"{TAG} My quiz" and got["description"] == "About AI" and got["editable"] is True
    assert got["owner_label"] == "Cikgu Ana" and got["questions"] == []
    for h in ({}, {"X-Edit-Key": "wrong"}, {"X-Edit-Key": qz["edit_key"][:-1]}):
        assert client.get(f"/api/live/quizzes/{pid}", headers=h).status_code == 403
        assert client.put(f"/api/live/quizzes/{pid}", headers=h, json={"name": "x"}).status_code == 403
        assert client.post(f"/api/live/quizzes/{pid}/questions", headers=h, json={
            "prompt": "p", "options": ["a", "b"], "correct_option": 0}).status_code == 403
        assert client.put(f"/api/live/quizzes/{pid}/order", headers=h, json={"question_ids": []}).status_code == 403
    assert client.get("/api/live/quizzes/987654321", headers=qz["K"]).status_code == 404
    # another quiz's key doesn't open this one
    other = new_quiz(client, name=f"{TAG} Other")
    assert client.get(f"/api/live/quizzes/{pid}", headers=other["K"]).status_code == 403
    # validation
    for bad in ({"name": "  "}, {"name": "x" * 101}, {"name": "ok", "topic": "math"}):
        assert client.post("/api/live/quizzes", json=bad).status_code == 422
    r = client.put(f"/api/live/quizzes/{pid}", headers=qz["K"], json={"name": f"{TAG} Renamed", "topic": "ai"})
    assert r.status_code == 200 and r.json()["name"] == f"{TAG} Renamed" and r.json()["topic"] == "ai"


def test_seeded_pack_is_read_only(client):
    seeded = _seeded_pack_id(client)
    assert client.get(f"/api/live/quizzes/{seeded['id']}").status_code == 403
    r = client.put(f"/api/live/quizzes/{seeded['id']}", headers={"X-Edit-Key": "anything"}, json={"name": "x"})
    assert r.status_code == 403 and "duplicate" in r.json()["detail"]


def test_packs_list_editable_flag(client):
    a, b = new_quiz(client, name=f"{TAG} A"), new_quiz(client, name=f"{TAG} B")
    add_q(client, a)
    anon = client.get("/api/live/packs").json()
    assert all(p["editable"] is False for p in anon)
    assert not {a["pack_id"], b["pack_id"]} & {p["id"] for p in anon}  # teacher quizzes are unlisted
    mine = client.get("/api/live/packs", headers={"X-Edit-Key": f"{a['edit_key']}, {b['edit_key']}"}).json()
    by = {p["id"]: p for p in mine}
    assert by[a["pack_id"]]["editable"] is True and by[b["pack_id"]]["editable"] is True
    assert by[a["pack_id"]]["question_counts"]["multiple_choice"] == 1
    assert mine[0]["id"] in (a["pack_id"], b["pack_id"])  # own quizzes first
    assert any(p["editable"] is False for p in mine)  # seeded ones still listed


def test_create_rate_limit(client, monkeypatch):
    monkeypatch.setattr(quiz, "create_limiter", quiz.live.RateLimiter(3, 3600))
    codes = []
    for i in range(4):
        r = client.post("/api/live/quizzes", json={"name": f"{TAG} rl{i}"})
        if r.status_code == 201:
            PACKS.add(r.json()["pack_id"])
        codes.append(r.status_code)
    assert codes == [201, 201, 201, 429]


# ------------------------------------------------------------------ questions
def test_question_crud_and_validation(client):
    qz = new_quiz(client)
    q = add_q(client, qz, options=(" True ", "False"), correct=1, time_limit_sec=10, points=200)
    assert q["options"] == ["True", "False"] and q["correct_option"] == 1 and q["points"] == 200
    assert q["time_limit_sec"] == 10 and q["sort_order"] == 1
    url = f"/api/live/quizzes/{qz['pack_id']}/questions"
    base = {"prompt": "p", "options": ["a", "b"], "correct_option": 0}
    for bad in ({"options": ["a"]}, {"options": ["a", "b", "c", "d", "e"]}, {"options": ["a", ""]},
                {"options": ["A", "a"]}, {"correct_option": 2}, {"correct_option": -1}, {"points": 150},
                {"time_limit_sec": 4}, {"time_limit_sec": 121}, {"prompt": "  "}):
        r = client.post(url, headers=qz["K"], json={**base, **bad})
        assert r.status_code == 422 and isinstance(r.json()["detail"], str), bad
    q2 = add_q(client, qz, prompt="Second")
    assert q2["sort_order"] == 2 and q2["points"] == 100 and q2["time_limit_sec"] == 20
    r = client.put(f"{url}/{q['id']}", headers=qz["K"], json={**base, "prompt": f"{TAG} edited",
                                                               "options": ["x", "y", "z"], "correct_option": 2})
    assert r.status_code == 200 and r.json()["options"] == ["x", "y", "z"] and r.json()["points"] == 100
    assert client.put(f"{url}/999999999", headers=qz["K"], json=base).status_code == 404
    got = client.get(f"/api/live/quizzes/{qz['pack_id']}", headers=qz["K"]).json()
    assert [x["id"] for x in got["questions"]] == [q["id"], q2["id"]]
    # a question of ANOTHER quiz can't be edited through this key
    other = new_quiz(client, name=f"{TAG} Other")
    oq = add_q(client, other)
    assert client.put(f"{url}/{oq['id']}", headers=qz["K"], json=base).status_code == 404
    assert client.delete(f"{url}/{oq['id']}", headers=qz["K"]).status_code == 404


def test_delete_vs_archive_and_play(client):
    qz = new_quiz(client)
    q1, q2 = add_q(client, qz, prompt="Played"), add_q(client, qz, prompt="Fresh")
    # the teacher quiz can be played in a live game (this "uses" both questions)
    r = client.post("/api/live/games", json={"pack_id": qz["pack_id"], "question_count": 2})
    assert r.status_code == 201, r.text
    GAMES.add(r.json()["game_id"])
    q3 = add_q(client, qz, prompt="Never played")
    url = f"/api/live/quizzes/{qz['pack_id']}/questions"
    r = client.delete(f"{url}/{q1['id']}", headers=qz["K"])
    assert r.status_code == 200 and r.json() == {"question_id": q1["id"], "deleted": False, "archived": True}
    r = client.delete(f"{url}/{q3['id']}", headers=qz["K"])
    assert r.json() == {"question_id": q3["id"], "deleted": True, "archived": False}
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        assert c.execute("SELECT is_active FROM question WHERE id = %s", (q1["id"],)).fetchone() == (False,)
        assert c.execute("SELECT 1 FROM question WHERE id = %s", (q3["id"],)).fetchone() is None
    assert [x["id"] for x in client.get(f"/api/live/quizzes/{qz['pack_id']}", headers=qz["K"]).json()["questions"]] \
        == [q2["id"]]
    assert client.delete(f"{url}/{q1['id']}", headers=qz["K"]).status_code == 404  # already archived


def test_duplicate_seeded_and_own(client):
    seeded = _seeded_pack_id(client)
    r = client.post(f"/api/live/quizzes/{seeded['id']}/duplicate")
    assert r.status_code == 201, r.text
    dup = r.json()
    PACKS.add(dup["pack_id"])
    assert dup["question_count"] == seeded["question_counts"]["multiple_choice"]
    got = client.get(f"/api/live/quizzes/{dup['pack_id']}", headers={"X-Edit-Key": dup["edit_key"]}).json()
    assert got["name"].endswith("(copy)") and len(got["questions"]) == dup["question_count"]
    assert [q["sort_order"] for q in got["questions"]] == list(range(1, dup["question_count"] + 1))
    # the copy is independent: editing it leaves the seeded pack alone
    qid = got["questions"][0]["id"]
    client.put(f"/api/live/quizzes/{dup['pack_id']}/questions/{qid}", headers={"X-Edit-Key": dup["edit_key"]},
               json={"prompt": f"{TAG} changed", "options": ["a", "b"], "correct_option": 0})
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        assert c.execute("SELECT COUNT(*) FROM question WHERE pack_id = %s AND prompt = %s",
                         (seeded["id"], f"{TAG} changed")).fetchone()[0] == 0
    # own quiz: key required to duplicate
    mine = new_quiz(client)
    add_q(client, mine)
    assert client.post(f"/api/live/quizzes/{mine['pack_id']}/duplicate").status_code == 403
    r = client.post(f"/api/live/quizzes/{mine['pack_id']}/duplicate", headers=mine["K"])
    assert r.status_code == 201 and r.json()["question_count"] == 1 and r.json()["edit_key"] != mine["edit_key"]
    PACKS.add(r.json()["pack_id"])
    assert client.post("/api/live/quizzes/987654321/duplicate").status_code == 404


# ------------------------------------------------------------------ reorder
def test_reorder(client):
    qz = new_quiz(client)
    ids = [add_q(client, qz, prompt=f"Q{i}")["id"] for i in range(3)]
    url = f"/api/live/quizzes/{qz['pack_id']}/order"
    r = client.put(url, headers=qz["K"], json={"question_ids": [ids[2], ids[0], ids[1]]})
    assert r.status_code == 200
    assert [(q["id"], q["sort_order"]) for q in r.json()["questions"]] == [(ids[2], 1), (ids[0], 2), (ids[1], 3)]
    for bad in ([ids[0], ids[1]], ids + [ids[0]], ids + [999999999], [ids[0], ids[0], ids[1]]):
        assert client.put(url, headers=qz["K"], json={"question_ids": bad}).status_code == 422, bad


def test_reorder_vs_delete_concurrency(client, server):
    """A reorder racing a delete on the same quiz: they serialise on the pack row lock. Either the reorder wins
    (200, then the delete succeeds) or the delete wins (the stale reorder gets 422). Never 500, never a gap."""
    outcomes = set()
    with httpx.Client(base_url=server, timeout=20) as h:
        for _ in range(8):
            qz = new_quiz(client)
            ids = [add_q(client, qz, prompt=f"C{i}")["id"] for i in range(4)]
            barrier = threading.Barrier(2)
            res = {}

            def do_reorder():
                barrier.wait()
                res["order"] = h.put(f"/api/live/quizzes/{qz['pack_id']}/order", headers=qz["K"],
                                     json={"question_ids": list(reversed(ids))}).status_code

            def do_delete():
                barrier.wait()
                res["delete"] = h.delete(f"/api/live/quizzes/{qz['pack_id']}/questions/{ids[1]}",
                                         headers=qz["K"]).status_code

            ts = [threading.Thread(target=do_reorder), threading.Thread(target=do_delete)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(20)
            assert res["delete"] == 200 and res["order"] in (200, 422), res
            outcomes.add(res["order"])
            got = client.get(f"/api/live/quizzes/{qz['pack_id']}", headers=qz["K"]).json()["questions"]
            assert [q["id"] for q in got] == [i for i in (reversed(ids) if res["order"] == 200 else ids)
                                              if i != ids[1]]
            assert len({q["sort_order"] for q in got}) == 3
    assert outcomes <= {200, 422}


def test_private_quiz_never_picked_by_unscoped_games(client):
    """'All packs' games (pack_id null) must not pick a teacher's private quiz — this is also what keeps other
    users' games on the shared dev DB away from the test suites' questions."""
    from app import live

    qz = new_quiz(client)
    mine = {add_q(client, qz, prompt=f"Private {i}")["id"] for i in range(4)}
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        flags = c.execute(f"SELECT q.id, {live.NOT_PRIVATE_SQL} FROM question q WHERE q.id = ANY(%s)",
                          (list(mine),)).fetchall()
    assert all(ok is False for _qid, ok in flags)
    for _ in range(5):
        r = client.post("/api/live/games", json={"question_count": 30})
        assert r.status_code == 201, r.text
        GAMES.add(r.json()["game_id"])
        with psycopg.connect(os.environ["DATABASE_URL"]) as c:
            picked = {x[0] for x in c.execute("SELECT question_id FROM live_question WHERE game_id = %s",
                                              (r.json()["game_id"],))}
        assert not picked & mine
    # picked explicitly, it plays
    r = client.post("/api/live/games", json={"pack_id": qz["pack_id"], "question_count": 4})
    assert r.status_code == 201
    GAMES.add(r.json()["game_id"])
