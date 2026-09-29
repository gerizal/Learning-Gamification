"""Integration tests for the LIVE GAME (/api/live) + multiple_choice classroom turns. Quiz only: speaking
questions are never picked, and speaking modes / audio uploads are rejected with 422.

Real dev PostgreSQL (DATABASE_URL) and a real uvicorn server in a background thread for SSE and the concurrency tests (so LISTEN/NOTIFY crosses "instances":
the TestClient app and the uvicorn app each run their own broker/event loop).

Every row created here is tagged ("[pytest-live]" titles / prompts, "pytest-live-" pack slugs) and deleted
by primary key at the end of the module.
"""
from __future__ import annotations

import csv
import io
import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:55432/playclass")
TAG = "[pytest-live]"

psycopg = pytest.importorskip("psycopg")
httpx = pytest.importorskip("httpx")


def _db_reachable() -> str | None:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as c:
            c.execute("SELECT 1 FROM live_game LIMIT 1")
        return None
    except Exception as exc:  # noqa: BLE001
        return f"DATABASE_URL unreachable or db/006_live.sql not applied: {exc.__class__.__name__}"


_reason = _db_reachable()
if _reason:
    pytest.skip(_reason, allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import live, quiz, scoring  # noqa: E402
from app.main import app  # noqa: E402
from tests._seed import insert_pack, insert_question  # noqa: E402

SPEAKING_422 = "speaking questions are not supported"

CREATED: dict[str, set] = {"game": set(), "pack": set(), "question": set(), "classroom": set()}

MCQ = [  # prompt suffix, options, correct
    ("What does AI stand for?", ["Artificial Intelligence", "Automatic Internet", "Apple Inside"], 0),
    ("Can AI make mistakes?", ["No, never", "Yes, sometimes"], 1),
    ("Who makes the final decision?", ["The robot", "Nobody", "People", "The phone"], 2),
]
SECRET_KW = "photosynthesis"
PACK_KEY = "pytest-live-key-" + uuid.uuid4().hex


# ------------------------------------------------------------------ cleanup (by PK, children first)
def _cleanup():
    games = [str(g) for g in CREATED["game"]]
    cls = list(CREATED["classroom"])
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        if games:
            c.execute("DELETE FROM live_answer WHERE game_id = ANY(%s::uuid[])", (games,))
            c.execute("DELETE FROM live_player WHERE game_id = ANY(%s::uuid[])", (games,))
            c.execute("DELETE FROM live_question WHERE game_id = ANY(%s::uuid[])", (games,))
            c.execute("DELETE FROM live_game WHERE id = ANY(%s::uuid[])", (games,))
        if cls:
            sids = [str(r[0]) for r in c.execute("SELECT id FROM class_session WHERE classroom_id = ANY(%s)",
                                                 (cls,)).fetchall()]
            c.execute("DELETE FROM class_attempt WHERE class_session_id = ANY(%s::uuid[])", (sids,))
            c.execute("DELETE FROM class_turn WHERE class_session_id = ANY(%s::uuid[])", (sids,))
            c.execute("DELETE FROM attendance WHERE class_session_id = ANY(%s::uuid[])", (sids,))
            c.execute("DELETE FROM team_member WHERE team_id IN (SELECT id FROM team "
                      "WHERE class_session_id = ANY(%s::uuid[]))", (sids,))
            c.execute("DELETE FROM team WHERE class_session_id = ANY(%s::uuid[])", (sids,))
            c.execute("DELETE FROM class_session WHERE id = ANY(%s::uuid[])", (sids,))
            c.execute("DELETE FROM student WHERE classroom_id = ANY(%s)", (cls,))
            c.execute("DELETE FROM classroom WHERE id = ANY(%s)", (cls,))
    # Questions/packs last. If someone else's game picked one of our questions meanwhile (shared dev DB),
    # we must not delete their rows: archive ours instead.
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        if CREATED["pack"]:  # questions inside our packs (teacher quizzes, duplicates) are ours too
            CREATED["question"] |= {r[0] for r in c.execute("SELECT id FROM question WHERE pack_id = ANY(%s)",
                                                              (list(CREATED["pack"]),)).fetchall()}
        for qid in CREATED["question"]:
            try:
                c.execute("DELETE FROM question WHERE id = %s", (qid,))
            except psycopg.errors.ForeignKeyViolation:
                c.execute("UPDATE question SET is_active = false WHERE id = %s", (qid,))
        for pid in CREATED["pack"]:
            try:
                c.execute("DELETE FROM question_pack WHERE id = %s", (pid,))
            except psycopg.errors.ForeignKeyViolation:
                c.execute("UPDATE question_pack SET is_active = false WHERE id = %s", (pid,))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    _cleanup()


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    live.join_limiter.clear()
    live.lookup_limiter.clear()
    yield
    live.join_limiter.clear()


@pytest.fixture(scope="module")
def server():
    """The real app on uvicorn in a thread (SSE + real concurrency)."""
    import uvicorn

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off",
                         loop="asyncio", timeout_graceful_shutdown=2)
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(10)


# ------------------------------------------------------------------ helpers
def _q(client, pack_id, **over):
    body = {"prompt": f"{TAG} Q", "difficulty": 1, "base_points": 100, "time_limit_sec": 20, "is_active": True,
            "sort_order": 0}
    body.update(over)
    q = insert_question(pack_id, **body)
    CREATED["question"].add(q["id"])
    return q


@pytest.fixture(scope="module")
def pack(client):
    # private (teacher-quiz-like): unscoped games of other users of the shared DB can't pick our questions
    p = insert_pack(slug=f"pytest-live-{uuid.uuid4().hex[:8]}", name=f"{TAG} Pack", topic="ai", description="d",
                    why_it_matters="w", edit_key_hash=quiz.hash_key(PACK_KEY))
    CREATED["pack"].add(p["id"])
    qs = {"mc": [], "speaking": {}}
    for text, opts, correct in MCQ:
        qs["mc"].append(_q(client, p["id"], prompt=f"{TAG} {text}", options=opts, correct_option=correct))
    # LEGACY speaking rows (pre-2026-09-28): must never be picked or counted
    qs["speaking"]["read_aloud"] = _q(client, p["id"], game_mode="read_aloud", prompt=f"{TAG} Read this",
                                      target_text="I like to eat rice")
    qs["speaking"]["quick_answer"] = _q(client, p["id"], game_mode="quick_answer",
                                        prompt=f"{TAG} How do plants make food from light?",
                                        keywords=[SECRET_KW])
    return {**p, "questions": qs}


def _correct_for(prompt: str) -> int:
    for text, _opts, correct in MCQ:
        if prompt == f"{TAG} {text}":
            return correct
    raise AssertionError(prompt)


def new_game(client, pack, modes=("multiple_choice",), n=1, **over):
    body = {"pack_id": pack["id"], "game_modes": list(modes), "question_count": n, "title": f"{TAG} game"}
    body.update(over)
    r = client.post("/api/live/games", json=body)
    assert r.status_code == 201, r.text
    g = r.json()
    CREATED["game"].add(g["game_id"])
    g["H"] = {"X-Host-Token": g["host_token"]}
    return g


def join(client, g, nick):
    r = client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": nick})
    assert r.status_code == 201, r.text
    p = r.json()
    p["P"] = {"X-Player-Token": p["player_token"]}
    return p


def host_state(client, g):
    r = client.get(f"/api/live/games/{g['pin']}/state", params={"host_token": g["host_token"]})
    assert r.status_code == 200, r.text
    return r.json()


def player_state(client, g, p):
    r = client.get(f"/api/live/games/{g['pin']}/state", params={"player_token": p["player_token"]})
    assert r.status_code == 200, r.text
    return r.json()


def nxt(client, g, st=None):
    st = st or host_state(client, g)
    r = client.post(f"/api/live/games/{g['pin']}/next", json={"status": st["status"], "index": st["index"]},
                    headers=g["H"])
    assert r.status_code == 200, r.text
    return r.json()


def answer_mc(client, g, p, choice, **extra):
    return client.post(f"/api/live/games/{g['pin']}/answer", json={"choice": choice, **extra}, headers=p["P"])


def shift_phase(g, seconds):
    """Pretend the current phase started `seconds` ago (our own test game row only)."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        c.execute("UPDATE live_game SET phase_started_at = clock_timestamp() - make_interval(secs => %s) "
                  "WHERE id = %s", (seconds, g["game_id"]))


def stored_answers(g):
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        return c.execute("SELECT player_id, idx, points, answer_ms, passed FROM live_answer WHERE game_id = %s "
                         "ORDER BY id", (g["game_id"],)).fetchall()


# ================================================================== quiz-only: speaking is not supported
def test_speaking_modes_rejected_at_create(client, pack):
    for modes in (["read_aloud"], ["multiple_choice", "quick_answer"], ["dance"]):
        r = client.post("/api/live/games", json={"pack_id": pack["id"], "game_modes": modes, "question_count": 1})
        assert r.status_code == 422 and SPEAKING_422 in r.json()["detail"], (modes, r.text)
    for mode in ("live", "self_paced"):
        r = client.post("/api/live/games", json={"pack_id": pack["id"], "game_modes": ["read_aloud"], "mode": mode})
        assert r.status_code == 422, mode


def test_legacy_routes_are_gone(client):
    for method, path in (("get", "/api/games"), ("get", "/api/users"), ("post", "/api/sessions"),
                         ("post", "/api/attempts"), ("get", "/api/leaderboard"), ("get", "/api/admin/stats"),
                         ("post", "/api/admin/questions"), ("get", "/practice"), ("get", "/admin")):
        assert client.request(method.upper(), path, json={}).status_code in (404, 405), path
    assert client.get("/api/health").json() == {"ok": True, "db": True}


# ================================================================== create / packs
def test_packs_list_has_mc_counts(client, pack):
    assert pack["id"] not in [p["id"] for p in client.get("/api/live/packs").json()]  # private: unlisted
    mine = next(p for p in client.get("/api/live/packs", headers={"X-Edit-Key": PACK_KEY}).json()
                if p["id"] == pack["id"])
    assert mine["editable"] is True
    assert mine["question_counts"] == {"multiple_choice": 3}  # legacy speaking rows are not counted


def test_create_game_defaults_and_errors(client, pack):
    r = client.post("/api/live/games", json={"pack_id": pack["id"], "question_count": 3})
    assert r.status_code == 201, r.text
    g = r.json()
    CREATED["game"].add(g["game_id"])
    assert len(g["pin"]) == 6 and g["pin"].isdigit()
    assert len(g["host_token"]) >= 43 and g["join_url"].endswith(f"/play?pin={g['pin']}")
    assert g["title"] == f"{TAG} Pack" and g["total"] == 3
    st = client.get(f"/api/live/games/{g['pin']}/state", params={"host_token": g["host_token"]}).json()
    assert st["status"] == "lobby" and st["index"] == -1 and st["total"] == 3 and st["question"] is None
    # multiple_choice only -> the 3 MC questions (the pack's legacy speaking rows are never picked)
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        modes = {r[0] for r in c.execute("SELECT q.game_mode FROM live_question lq JOIN question q "
                                         "ON q.id = lq.question_id WHERE lq.game_id = %s", (g["game_id"],))}
    assert modes == {"multiple_choice"}
    # not enough questions -> 422 ; bad input -> 422 ; unknown pack -> 404
    r = client.post("/api/live/games", json={"pack_id": pack["id"], "question_count": 4})
    assert r.status_code == 422 and "Not enough questions" in r.json()["detail"]
    for bad in ({"question_count": 0}, {"question_count": 31}, {"game_modes": []}, {"game_modes": ["dance"]},
                {"game_modes": ["read_aloud"]}):
        assert client.post("/api/live/games", json={"pack_id": pack["id"], **bad}).status_code == 422, bad
    assert client.post("/api/live/games", json={"pack_id": 987654321}).status_code == 404
    # public lookup
    r = client.get(f"/api/live/games/{g['pin']}")
    assert r.status_code == 200 and r.json() == {"pin": g["pin"], "title": g["title"], "status": "lobby",
                                                 "joinable": True}
    assert client.get("/api/live/games/12ab56").status_code == 404


def test_archived_pack_is_422(client):
    p = insert_pack(slug=f"pytest-live-{uuid.uuid4().hex[:8]}", name=f"{TAG} Old", topic="general", is_active=False)
    CREATED["pack"].add(p["id"])
    assert client.post("/api/live/games", json={"pack_id": p["id"]}).status_code == 422


# ================================================================== join
def test_join_rules(client, pack):
    g = new_game(client, pack)
    a = join(client, g, "  Ali   Baba ")
    assert a["nickname"] == "Ali Baba" and len(a["player_token"]) >= 43
    r = client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": "ali baba"})
    assert r.status_code == 409 and r.json()["detail"] == "name taken"
    for bad in ("", "   ", "x" * 21):
        assert client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": bad}).status_code == 422
    assert client.post(f"/api/live/games/{g['pin']}/join", json={}).status_code == 422
    assert join(client, g, "x" * 20)["nickname"] == "x" * 20
    assert client.post("/api/live/games/000000/join", json={"nickname": "Zed"}).status_code in (404, 409)
    assert client.post("/api/live/games/abc/join", json={"nickname": "Zed"}).status_code == 404
    st = host_state(client, g)
    assert st["players_count"] == 2 and [p["nickname"] for p in st["players"]] == ["Ali Baba", "x" * 20]
    # ended -> 409
    assert client.post(f"/api/live/games/{g['pin']}/end", headers=g["H"]).status_code == 200
    r = client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": "Late"})
    assert r.status_code == 409


def test_join_rate_limit(client, pack):
    g = new_game(client, pack)
    codes = [client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": f"R{i}"}).status_code
             for i in range(11)]
    assert codes[:10] == [201] * 10 and codes[10] == 429


def test_late_join_can_answer_current_question(client, pack):
    g = new_game(client, pack, n=2)
    early = join(client, g, "Early")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    st = player_state(client, g, early)
    assert answer_mc(client, g, early, _correct_for(st["question"]["prompt"])).status_code == 200
    nxt(client, g)  # reveal: Early scored
    late = join(client, g, "Late")  # joins after start: allowed, starts at 0
    ps = player_state(client, g, late)
    assert ps["me"]["score"] == 0 and ps["me"]["last_result"] is None and ps["status"] == "reveal"
    assert ps["me"]["rank"] == 2
    nxt(client, g)
    nxt(client, g)  # question 2
    ps = player_state(client, g, late)
    assert ps["status"] == "question" and ps["index"] == 1
    assert answer_mc(client, g, late, _correct_for(ps["question"]["prompt"])).status_code == 200
    nxt(client, g)
    assert player_state(client, g, late)["me"]["score"] > 0


# ================================================================== auth
def test_tokens_and_roles(client, pack):
    g = new_game(client, pack)
    p = join(client, g, "Tok")
    pin = g["pin"]
    assert client.get(f"/api/live/games/{pin}/state").status_code == 403
    assert client.get(f"/api/live/games/{pin}/state", params={"host_token": "nope"}).status_code == 403
    assert client.get(f"/api/live/games/{pin}/state", params={"player_token": "nope"}).status_code == 403
    assert client.get("/api/live/games/999999x/state", params={"host_token": "x"}).status_code == 404
    # host actions need X-Host-Token (a player token is not enough)
    for path in ("start", "next", "end"):
        assert client.post(f"/api/live/games/{pin}/{path}").status_code == 403
        assert client.post(f"/api/live/games/{pin}/{path}",
                           headers={"X-Host-Token": p["player_token"]}).status_code == 403
    assert client.post(f"/api/live/games/{pin}/players/{p['player_id']}/kick").status_code == 403
    assert client.patch(f"/api/live/games/{pin}/players/{p['player_id']}", json={"nickname": "x"}).status_code == 403
    assert client.get(f"/api/live/games/{pin}/report.csv", params={"host_token": "nope"}).status_code == 403
    # answer needs X-Player-Token (the host token is not a player)
    client.post(f"/api/live/games/{pin}/start", headers=g["H"])
    assert client.post(f"/api/live/games/{pin}/answer", json={"choice": 0}).status_code == 403
    assert client.post(f"/api/live/games/{pin}/answer", json={"choice": 0},
                       headers={"X-Player-Token": g["host_token"]}).status_code == 403
    # no secret tokens in any state
    hs, ps = host_state(client, g), player_state(client, g, p)
    for blob in (json.dumps(hs), json.dumps(ps)):
        assert g["host_token"] not in blob and p["player_token"] not in blob and "token" not in blob


# ================================================================== full MC flow, reveal, leaderboard, no leaks
def test_mc_flow_reveal_leaderboard_and_no_leaks(client, pack):
    g = new_game(client, pack, n=3, instant_feedback=False)  # Kahoot-like: results only from reveal on
    a, b, c = join(client, g, "Aina"), join(client, g, "Budi"), join(client, g, "Chen")
    # answers only in the question phase
    assert answer_mc(client, g, a, 0).status_code == 409
    r = client.post(f"/api/live/games/{g['pin']}/next", json={}, headers=g["H"])
    assert r.status_code == 409  # lobby: use /start
    st = client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"]).json()
    assert st["status"] == "question" and st["index"] == 0 and st["answered_count"] == 0
    assert client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"]).status_code == 409

    ps = player_state(client, g, a)
    q = ps["question"]
    correct = _correct_for(q["prompt"])
    wrong = (correct + 1) % len(q["options"])
    assert q["game_mode"] == "multiple_choice" and len(q["options"]) >= 2 and q["time_limit_sec"] == 20
    # NO LEAK before reveal: neither player nor host (projector) sees the correct option
    for blob in (ps, host_state(client, g)):
        s = json.dumps(blob)
        assert "correct_option" not in s and '"correct"' not in s and blob["reveal"] is None
        assert "option_text" not in s
    assert "players" not in ps and "me" in ps and "summary" not in ps
    assert ps["me"]["answered_current"] is False and ps["me"]["last_result"] is None

    # validation
    assert answer_mc(client, g, a, len(q["options"])).status_code == 422
    assert answer_mc(client, g, a, None).status_code == 422
    assert answer_mc(client, g, a, "x").status_code == 422
    assert answer_mc(client, g, a, correct, idx=5).status_code == 409  # stale client idx

    assert answer_mc(client, g, a, correct).json() == {"accepted": True, "result": None}
    r = answer_mc(client, g, a, wrong)
    assert r.status_code == 409 and r.json()["detail"] == "Already answered"
    shift_phase(g, 10)  # Budi answers "10 s later"
    assert answer_mc(client, g, b, wrong, idx=0).status_code == 200
    # still hidden: score + result only after reveal (suspense)
    ps = player_state(client, g, a)
    assert ps["me"]["answered_current"] is True and ps["me"]["last_result"] is None and ps["me"]["score"] == 0
    hs = host_state(client, g)
    assert hs["answered_count"] == 2 and hs["players_count"] == 3 and hs["reveal"] is None
    assert all(p["score"] == 0 for p in hs["players"])
    assert {p["nickname"]: p["answered"] for p in hs["players"]} == {"Aina": True, "Budi": True, "Chen": False}

    # -> reveal
    hs = nxt(client, g)
    assert hs["status"] == "reveal" and hs["index"] == 0
    rv = hs["reveal"]
    assert rv["correct"] == {"option": correct, "option_text": q["options"][correct]}
    assert rv["distribution"]["great"] == 1 and rv["distribution"]["retry"] == 1
    assert rv["distribution"]["ok"] == 0 and rv["distribution"]["no_answer"] == 1
    assert sum(rv["distribution"]["options"]) == 2 and rv["distribution"]["options"][correct] == 1
    assert [t["nickname"] for t in rv["top"]] == ["Aina"]
    rows = {r[0]: r for r in stored_answers(g)}
    a_pts = rows[a["player_id"]][2]
    expect = scoring.live_points(base_points=100, difficulty=1, accuracy=100, passed=True,
                                 answer_ms=rows[a["player_id"]][3], time_limit_sec=20, streak=1)["points"]
    assert a_pts == expect and 95 <= a_pts <= 100 and rows[b["player_id"]][2] == 0
    ps = player_state(client, g, a)
    assert ps["reveal"] == {"correct": {"option": correct, "option_text": q["options"][correct]}}
    lr = ps["me"]["last_result"]
    assert lr["passed"] is True and lr["points"] == a_pts and lr["stars"] == 3 and lr["choice"] == correct
    assert ps["me"]["score"] == a_pts and ps["me"]["rank"] == 1
    assert player_state(client, g, c)["me"]["last_result"] is None
    # after the question closed, answers are rejected
    assert answer_mc(client, g, c, correct).status_code == 409

    # -> leaderboard (Budi and Chen tie at 0: shared rank 2)
    hs = nxt(client, g)
    assert hs["status"] == "leaderboard"
    lb = hs["leaderboard"]["top"]
    assert [(r["rank"], r["nickname"], r["score"]) for r in lb] == [(1, "Aina", a_pts), (2, "Budi", 0), (2, "Chen", 0)]
    assert all(r["delta_rank"] == 0 for r in lb)  # first question: no rank change shown
    pl = player_state(client, g, b)["leaderboard"]["top"]
    assert pl[0] == {"rank": 1, "nickname": "Aina", "score": a_pts, "delta_rank": 0}

    # question 2: Chen answers right instantly, Aina wrong -> Chen overtakes Budi
    hs = nxt(client, g)
    assert hs["status"] == "question" and hs["index"] == 1 and hs["reveal"] is None
    q2 = player_state(client, g, c)["question"]
    c2 = _correct_for(q2["prompt"])
    assert answer_mc(client, g, c, c2).status_code == 200
    assert answer_mc(client, g, a, (c2 + 1) % len(q2["options"])).status_code == 200
    nxt(client, g)
    lb = nxt(client, g)["leaderboard"]["top"]
    by = {r["nickname"]: r for r in lb}
    assert by["Chen"]["rank"] in (1, 2) and by["Chen"]["delta_rank"] == 2 - by["Chen"]["rank"]  # was tied 2nd
    assert by["Budi"]["rank"] == 3 and by["Budi"]["delta_rank"] == -1
    # streak: Aina failed q2 -> streak reset
    assert player_state(client, g, a)["me"]["streak"] == 0 and player_state(client, g, c)["me"]["streak"] == 1

    # question 3 then leaderboard then ended
    nxt(client, g)
    nxt(client, g)
    assert nxt(client, g)["status"] == "leaderboard"
    end = nxt(client, g)
    assert end["status"] == "ended" and end["leaderboard"]["top"] and end["summary"] == {"joined": 3, "answered_any": 3}
    r = client.post(f"/api/live/games/{g['pin']}/next", json={}, headers=g["H"])
    assert r.status_code == 409
    assert client.post(f"/api/live/games/{g['pin']}/end", headers=g["H"]).status_code == 200  # idempotent
    fin = player_state(client, g, c)
    assert fin["status"] == "ended" and fin["me"]["rank"] >= 1 and fin["question"] is None


def test_audio_upload_and_legacy_speaking_question_rejected(client, pack):
    g = new_game(client, pack, n=1)
    p = join(client, g, "Mic")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    url = f"/api/live/games/{g['pin']}/answer"
    r = client.post(url, data={"idx": "0"}, files={"audio": ("a.wav", b"RIFF....WAVE", "audio/wav")}, headers=p["P"])
    assert r.status_code == 422 and r.json()["detail"] == SPEAKING_422
    assert stored_answers(g) == []
    # a game whose question row is a legacy speaking question (created before 2026-09-28)
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        c.execute("UPDATE live_question SET question_id = %s WHERE game_id = %s AND idx = 0",
                  (pack["questions"]["speaking"]["read_aloud"]["id"], g["game_id"]))
    r = answer_mc(client, g, p, 0)
    assert r.status_code == 422 and r.json()["detail"] == SPEAKING_422
    ps = player_state(client, g, p)
    assert ps["question"]["target_text"] is None and ps["question"]["options"] is None
    assert host_state(client, g)["answered_count"] == 0


def test_time_limit_grace_and_speed_factor(client, pack):
    g = new_game(client, pack, n=1)
    early, grace, late = join(client, g, "Fast"), join(client, g, "Grace"), join(client, g, "Slow")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    q = player_state(client, g, early)["question"]
    ok = _correct_for(q["prompt"])
    shift_phase(g, 5)  # answer at ~5 s of 20 -> factor 0.875
    assert answer_mc(client, g, early, ok).status_code == 200
    shift_phase(g, 21.5)  # inside the 3 s grace -> accepted, factor clamped to 0.5
    assert answer_mc(client, g, grace, ok).status_code == 200
    shift_phase(g, 23.5)  # beyond limit + grace -> 409
    r = answer_mc(client, g, late, ok)
    assert r.status_code == 409 and r.json()["detail"] == "Time is up"
    rows = {r[0]: r for r in stored_answers(g)}
    e, gr = rows[early["player_id"]], rows[grace["player_id"]]
    assert 5000 <= e[3] < 6500 and e[2] == round(100 * (1 - 0.5 * e[3] / 20000))
    assert 21500 <= gr[3] < 23000 and gr[2] == 50
    assert late["player_id"] not in rows


def test_streak_bonus_over_questions(client, pack):
    g = new_game(client, pack, n=3)
    p = join(client, g, "Streaky")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    for i in range(3):
        q = player_state(client, g, p)["question"]
        assert answer_mc(client, g, p, _correct_for(q["prompt"])).status_code == 200
        nxt(client, g)  # reveal
        lr = player_state(client, g, p)["me"]["last_result"]
        assert lr["streak"] == i + 1 and lr["streak_multiplier"] == round(1 + 0.1 * i, 2)
        if i < 2:
            nxt(client, g)
            nxt(client, g)


def test_kick_and_rename(client, pack):
    g = new_game(client, pack)
    a, b = join(client, g, "Anna"), join(client, g, "Troll")
    pin = g["pin"]
    hs = client.patch(f"/api/live/games/{pin}/players/{a['player_id']}", json={"nickname": " Anna B "},
                      headers=g["H"]).json()
    assert [p["nickname"] for p in hs["players"]] == ["Anna B", "Troll"]
    r = client.patch(f"/api/live/games/{pin}/players/{a['player_id']}", json={"nickname": "troll"}, headers=g["H"])
    assert r.status_code == 409
    assert client.patch(f"/api/live/games/{pin}/players/{a['player_id']}", json={"nickname": ""},
                        headers=g["H"]).status_code == 422
    assert client.patch(f"/api/live/games/{pin}/players/99999999", json={"nickname": "Zz"},
                        headers=g["H"]).status_code == 404
    hs = client.post(f"/api/live/games/{pin}/players/{b['player_id']}/kick", headers=g["H"]).json()
    assert hs["players_count"] == 1 and [p["nickname"] for p in hs["players"]] == ["Anna B"]
    assert client.post(f"/api/live/games/{pin}/players/{b['player_id']}/kick", headers=g["H"]).status_code == 200
    assert client.post(f"/api/live/games/{pin}/players/99999999/kick", headers=g["H"]).status_code == 404
    r = client.get(f"/api/live/games/{pin}/state", params={"player_token": b["player_token"]})
    assert r.status_code == 403 and "removed" in r.json()["detail"]
    # the kicked name stays reserved in this game
    assert client.post(f"/api/live/games/{pin}/join", json={"nickname": "Troll"}).status_code == 409
    client.post(f"/api/live/games/{pin}/start", headers=g["H"])
    assert answer_mc(client, g, b, 0).status_code == 403
    # a player's rename is visible to that player
    assert player_state(client, g, a)["me"]["nickname"] == "Anna B"


def test_end_during_question_keeps_points(client, pack):
    g = new_game(client, pack, n=3)
    p = join(client, g, "Ender")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    q = player_state(client, g, p)["question"]
    assert answer_mc(client, g, p, _correct_for(q["prompt"])).status_code == 200
    hs = client.post(f"/api/live/games/{g['pin']}/end", headers=g["H"]).json()
    assert hs["status"] == "ended" and hs["leaderboard"]["top"][0]["score"] > 0
    assert answer_mc(client, g, p, 0).status_code == 409


def test_next_debounce_without_expectation(client, pack):
    g = new_game(client, pack, n=2)
    join(client, g, "Deb")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    time.sleep(0.8)
    assert client.post(f"/api/live/games/{g['pin']}/next", headers=g["H"]).status_code == 200
    r = client.post(f"/api/live/games/{g['pin']}/next", headers=g["H"])  # immediate 2nd click
    assert r.status_code == 409
    assert host_state(client, g)["status"] == "reveal"
    # stale expectation -> 409
    r = client.post(f"/api/live/games/{g['pin']}/next", json={"status": "question", "index": 0}, headers=g["H"])
    assert r.status_code == 409


# ================================================================== concurrency (real server, threads)
def _parallel(n, fn):
    barrier = threading.Barrier(n)
    out = [None] * n

    def run(i):
        barrier.wait()
        out[i] = fn(i)

    ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    return out


def test_double_next_advances_once(client, server, pack):
    g = new_game(client, pack, n=2)
    join(client, g, "Dbl")
    with httpx.Client(base_url=server, timeout=20) as h:
        codes = _parallel(2, lambda i: h.post(f"/api/live/games/{g['pin']}/start", headers=g["H"]).status_code)
        assert sorted(codes) == [200, 409]
        body = {"status": "question", "index": 0}
        codes = _parallel(3, lambda i: h.post(f"/api/live/games/{g['pin']}/next", json=body,
                                              headers=g["H"]).status_code)
        assert sorted(codes) == [200, 409, 409]
        st = host_state(client, g)
        assert st["status"] == "reveal" and st["index"] == 0
        time.sleep(0.8)  # plain double-click without body (debounce)
        codes = _parallel(2, lambda i: h.post(f"/api/live/games/{g['pin']}/next",
                                              headers=g["H"]).status_code)
        assert sorted(codes) == [200, 409]
        assert host_state(client, g)["status"] == "leaderboard"


def test_simultaneous_answers_one_wins(client, server, pack):
    g = new_game(client, pack, n=1)
    p = join(client, g, "Twin")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    with httpx.Client(base_url=server, timeout=20) as h:
        res = _parallel(2, lambda i: h.post(f"/api/live/games/{g['pin']}/answer", json={"choice": i},
                                            headers=p["P"]))
    assert sorted(r.status_code for r in res) == [200, 409]
    assert len(stored_answers(g)) == 1


# ================================================================== SSE
def _sse_reader(url, sink: list, stop: threading.Event, ready: threading.Event):
    try:
        with httpx.Client(timeout=httpx.Timeout(20, read=20)) as h, h.stream("GET", url) as r:
            sink.append(("status", r.status_code, r.headers.get("content-type")))
            ready.set()
            event = None
            for line in r.iter_lines():
                if line.startswith(":"):
                    sink.append(("comment", line))
                elif line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event:
                    sink.append((event, json.loads(line[5:])))
                if stop.is_set():
                    break
    except Exception as exc:  # noqa: BLE001
        sink.append(("error", repr(exc)))
        ready.set()


def _wait_for(pred, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def _subscribers() -> int:
    return sum(b.subscriber_count() for b in list(live._brokers.values()))


def test_sse_state_after_join_heartbeat_and_cleanup(client, server, pack, monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SEC", 1.0)
    g = new_game(client, pack, n=1)
    sink, stop, ready = [], threading.Event(), threading.Event()
    url = f"{server}/api/live/games/{g['pin']}/events?host_token={g['host_token']}"
    t = threading.Thread(target=_sse_reader, args=(url, sink, stop, ready), daemon=True)
    t.start()
    assert ready.wait(10)
    assert sink[0][0] == "status" and sink[0][1] == 200 and sink[0][2].startswith("text/event-stream")
    assert _wait_for(lambda: any(e[0] == "state" for e in sink))
    first = next(e[1] for e in sink if e[0] == "state")
    assert first["status"] == "lobby" and first["players_count"] == 0
    # a join through the OTHER app instance (TestClient) reaches this stream via LISTEN/NOTIFY
    join(client, g, "Sse")
    assert _wait_for(lambda: any(e[0] == "state" and e[1]["players_count"] == 1 for e in sink))
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    assert _wait_for(lambda: any(e[0] == "state" and e[1]["status"] == "question" for e in sink))
    assert _wait_for(lambda: any(e[0] == "comment" and "ping" in e[1] for e in sink), timeout=4)
    assert not any(e[0] == "error" for e in sink), sink
    stop.set()
    t.join(5)
    assert _wait_for(lambda: _subscribers() == 0, timeout=6), "SSE subscription not cleaned up"


def test_sse_player_stream_and_kick(client, server, pack, monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SEC", 1.0)
    g = new_game(client, pack, n=1)
    p = join(client, g, "Streamer")
    sink, stop, ready = [], threading.Event(), threading.Event()
    url = f"{server}/api/live/games/{g['pin']}/events?player_token={p['player_token']}"
    t = threading.Thread(target=_sse_reader, args=(url, sink, stop, ready), daemon=True)
    t.start()
    assert ready.wait(10) and _wait_for(lambda: any(e[0] == "state" for e in sink))
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    assert _wait_for(lambda: any(e[0] == "state" and e[1]["status"] == "question" for e in sink))
    q_state = next(e[1] for e in sink if e[0] == "state" and e[1]["status"] == "question")
    assert "correct_option" not in json.dumps(q_state) and "players" not in q_state and q_state["me"]["id"]
    client.post(f"/api/live/games/{g['pin']}/players/{p['player_id']}/kick", headers=g["H"])
    assert _wait_for(lambda: any(e[0] == "kicked" for e in sink))
    stop.set()
    t.join(5)
    # bad tokens are plain HTTP errors, not streams
    with httpx.Client(base_url=server, timeout=10) as h:
        assert h.get(f"/api/live/games/{g['pin']}/events?host_token=nope").status_code == 403
        assert h.get(f"/api/live/games/{g['pin']}/events?player_token={p['player_token']}").status_code == 403
        assert h.get("/api/live/games/123/events").status_code == 404


# ================================================================== CSV report
def test_report_csv(client, pack):
    g = new_game(client, pack, n=2, teacher_name="Cikgu Ana", school="SK Test", program="Apptitude")
    a, b, k = join(client, g, "Alya"), join(client, g, "Bala"), join(client, g, "Kicked")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    for _ in range(2):
        q = player_state(client, g, a)["question"]
        ok = _correct_for(q["prompt"])
        assert answer_mc(client, g, a, ok).status_code == 200
        nxt(client, g)
        nxt(client, g)
        nxt(client, g)
    client.post(f"/api/live/games/{g['pin']}/players/{k['player_id']}/kick", headers=g["H"])
    r = client.get(f"/api/live/games/{g['pin']}/report.csv", params={"host_token": g["host_token"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert f"live-" in r.headers["content-disposition"] and g["pin"] in r.headers["content-disposition"]
    raw = r.content.decode("utf-8")
    assert raw.startswith("﻿") and "\r\n" in raw
    rows = list(csv.DictReader(io.StringIO(raw.lstrip("﻿"))))
    assert list(rows[0].keys()) == live.CSV_COLS
    assert [r["nickname"] for r in rows] == ["Alya", "Bala"]  # kicked players are not in the report
    alya, bala = rows
    assert alya["answered"] == "2" and alya["correct"] == "2" and alya["avg_accuracy"] == "100.00"
    assert alya["rank"] == "1" and int(alya["score"]) > 0
    assert bala["answered"] == "0" and bala["avg_accuracy"] == "" and bala["rank"] == "2" and bala["score"] == "0"
    assert alya["teacher_name"] == "Cikgu Ana" and alya["school"] == "SK Test" and alya["program"] == "Apptitude"
    assert alya["pack"] == f"{TAG} Pack" and alya["questions"] == "2" and alya["pin"] == g["pin"]
    # header token works too
    assert client.get(f"/api/live/games/{g['pin']}/report.csv", headers=g["H"]).status_code == 200


# ================================================================== pages
def test_pages(client):
    for path, name in (("/", None), ("/host", "host.html"), ("/play", "play.html")):
        r = client.get(path)
        if name is None or (ROOT / "static" / name).is_file():
            assert r.status_code == 200 and "text/html" in r.headers["content-type"], path
        else:
            assert r.status_code == 404, path


# ================================================================== classroom: multiple_choice turns
def test_classroom_quiz_turns(client, pack):
    r = client.post("/api/class/classrooms", json={"name": f"{TAG} Kelas"})
    assert r.status_code == 201
    cid = r.json()["id"]
    CREATED["classroom"].add(cid)
    added = client.post(f"/api/class/classrooms/{cid}/students", json={"names": ["Ali", "Bee", "Cai", "Dee"]}).json()
    ids = [s["id"] for s in added["added"]]
    # game_modes omitted -> multiple_choice only
    r = client.post("/api/class/sessions", json={"classroom_id": cid, "pack_id": pack["id"], "team_count": 2,
                                                  "rounds": 1, "present_student_ids": ids})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["game_modes"] == ["multiple_choice"]
    assert all(t["question"]["game_mode"] == "multiple_choice" for t in s["turns"])
    t1 = s["turns"][0]
    assert len(t1["question"]["options"]) >= 2 and "correct_option" not in json.dumps(s)
    correct = _correct_for(t1["question"]["prompt"])
    team1 = next(t for t in s["teams"] if t["id"] == t1["team_id"])
    sid = team1["members"][0]["student_id"]
    url = f"/api/class/sessions/{s['id']}/turns/1/attempts"
    assert client.post(url, data={"student_id": sid}).status_code == 422  # choice missing
    assert client.post(url, data={"student_id": sid, "choice": "9"}).status_code == 422
    r = client.post(url, data={"student_id": sid, "choice": str(correct), "duration_ms": "1500"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["accuracy"] == 100.0 and res["passed"] and res["points"] > 0
    assert res["turn"]["attempts_left"] == 0 and res["team"]["score"] == res["points"] and res["streak"] == 1
    # one attempt per quiz turn -> the correct option can be shown right away
    assert res["feedback"]["correct_option"] == correct
    assert res["feedback"]["correct_option_text"] == t1["question"]["options"][correct]
    assert res["feedback"]["correct"] is True and res["feedback"]["choice"] == correct
    r = client.post(url, data={"student_id": sid, "choice": str(correct)})
    assert r.status_code == 409 and r.json()["detail"] == "one attempt for quiz"
    # a wrong quiz answer on the next turn: 0 points, team streak 0
    client.post(f"/api/class/sessions/{s['id']}/turns/1/next", json={})
    t2 = s["turns"][1]
    team2 = next(t for t in s["teams"] if t["id"] == t2["team_id"])
    wrong = (_correct_for(t2["question"]["prompt"]) + 1) % len(t2["question"]["options"])
    r = client.post(f"/api/class/sessions/{s['id']}/turns/2/attempts",
                    data={"student_id": team2["members"][0]["student_id"], "choice": str(wrong)})
    assert r.status_code == 200 and r.json()["points"] == 0 and r.json()["passed"] is False
    assert r.json()["feedback"]["correct_option"] == _correct_for(t2["question"]["prompt"])
    assert r.json()["team"]["streak"] == 0
    # an explicit speaking mode is rejected
    r = client.post("/api/class/sessions", json={"classroom_id": cid, "pack_id": pack["id"], "team_count": 2,
                                                  "rounds": 1, "present_student_ids": ids,
                                                  "game_modes": ["read_aloud"]})
    assert r.status_code == 422 and SPEAKING_422 in r.json()["detail"]


# ================================================================== instant feedback + live leaderboard
def _db_scores(g):
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        return {r[0]: (r[1], r[2]) for r in c.execute(
            """SELECT p.id, p.score, COALESCE(SUM(a.points) FILTER (WHERE a.applied), 0)::int
                 FROM live_player p LEFT JOIN live_answer a ON a.player_id = p.id
                WHERE p.game_id = %s GROUP BY p.id""", (g["game_id"],)).fetchall()}


def test_instant_feedback_default_live_scores(client, pack):
    g = new_game(client, pack, n=2)  # instant_feedback defaults to TRUE
    a, b = join(client, g, "Quick"), join(client, g, "Later")
    st = client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"]).json()
    assert st["settings"] == {"allow_rename": True, "instant_feedback": True}
    q = player_state(client, g, a)["question"]
    ok = _correct_for(q["prompt"])
    r = answer_mc(client, g, a, ok).json()
    assert r["accepted"] and r["result"]["passed"] and r["result"]["points"] > 0
    assert r["result"]["correct"] == {"option": ok, "option_text": q["options"][ok]}
    pts = r["result"]["points"]
    # the player sees the result + score + rank right away, still in the question phase
    ps = player_state(client, g, a)
    assert ps["status"] == "question" and ps["me"]["score"] == pts and ps["me"]["rank"] == 1
    assert ps["me"]["last_result"]["correct"]["option"] == ok and ps["reveal"] is None
    assert ps["leaderboard"]["top"][0] == {"rank": 1, "nickname": "Quick", "score": pts, "delta_rank": 0}
    assert ps["leaderboard"]["me"] == {"rank": 1, "score": pts, "above": None}
    # a player who has not answered yet learns nothing about the correct option
    pb = player_state(client, g, b)
    assert pb["me"]["last_result"] is None and "correct" not in json.dumps(pb) and "option_text" not in json.dumps(pb)
    assert pb["leaderboard"]["me"] == {"rank": 2, "score": 0, "above": {"nickname": "Quick", "score_gap": pts}}
    # host: live leaderboard, but the projector still hides the answer until reveal
    hs = host_state(client, g)
    assert hs["leaderboard"]["top"][0]["nickname"] == "Quick" and hs["players"][0]["score"] == pts
    assert hs["reveal"] is None and "correct_option" not in json.dumps(hs) and "option_text" not in json.dumps(hs)
    # closing the question does NOT add the points a second time
    nxt(client, g)
    assert player_state(client, g, a)["me"]["score"] == pts
    assert _db_scores(g)[a["player_id"]] == (pts, pts)


def test_toggle_instant_mid_question_applies_exactly_once(client, pack):
    g = new_game(client, pack, n=2, instant_feedback=False)
    a, b, c = join(client, g, "Ann"), join(client, g, "Bob"), join(client, g, "Cid")
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    ok = _correct_for(player_state(client, g, a)["question"]["prompt"])
    settings = f"/api/live/games/{g['pin']}/settings"
    assert answer_mc(client, g, a, ok).json()["result"] is None           # deferred: stored, not applied
    assert player_state(client, g, a)["me"]["score"] == 0
    hs = client.patch(settings, json={"instant_feedback": True}, headers=g["H"]).json()   # -> applies Ann now
    assert hs["settings"]["instant_feedback"] is True
    ann = player_state(client, g, a)["me"]
    assert ann["score"] > 0 and ann["last_result"]["points"] == ann["score"]
    assert answer_mc(client, g, b, ok).json()["result"]["points"] > 0    # instant: applied at submit
    assert client.patch(settings, json={"instant_feedback": True}, headers=g["H"]).status_code == 200  # no-op
    client.patch(settings, json={"instant_feedback": False}, headers=g["H"])
    assert answer_mc(client, g, c, ok).json()["result"] is None           # deferred again
    assert player_state(client, g, c)["me"]["score"] == 0
    nxt(client, g)                                                        # close: only Cid is applied now
    sc = _db_scores(g)
    rows = {r[0]: r[2] for r in stored_answers(g)}
    for p in (a, b, c):
        assert sc[p["player_id"]] == (rows[p["player_id"]], rows[p["player_id"]]), p["nickname"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        assert conn.execute("SELECT bool_and(applied) FROM live_answer WHERE game_id = %s",
                            (g["game_id"],)).fetchone()[0] is True
    # settings auth/validation
    assert client.patch(settings, json={"instant_feedback": True}).status_code == 403
    assert client.patch(settings, json={"instant_feedback": "maybe"}, headers=g["H"]).status_code == 422


def test_leaderboard_every_phase_and_rank_changes(client, pack):
    g = new_game(client, pack, n=3)
    a, b, c = join(client, g, "Aa"), join(client, g, "Bb"), join(client, g, "Cc")
    ps = player_state(client, g, b)  # lobby: everyone 0, shared rank 1
    assert ps["status"] == "lobby" and len(ps["leaderboard"]["top"]) == 3
    assert ps["leaderboard"]["me"]["rank"] == 1 and ps["leaderboard"]["me"]["above"]["score_gap"] == 0
    hs = host_state(client, g)
    assert hs["leaderboard"]["rank_changes"] == [] and len(hs["leaderboard"]["top"]) == 3
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    ok = _correct_for(player_state(client, g, a)["question"]["prompt"])
    answer_mc(client, g, a, ok)
    nxt(client, g), nxt(client, g), nxt(client, g)  # -> question 2
    # q2: Cc answers correctly -> moves from rank 2 to rank 2/1; Bb drops to 3
    ok2 = _correct_for(player_state(client, g, c)["question"]["prompt"])
    answer_mc(client, g, c, ok2)
    hs = host_state(client, g)
    moves = {m["nickname"]: (m["from"], m["to"]) for m in hs["leaderboard"]["rank_changes"]}
    assert moves["Bb"] == (2, 3) and moves["Cc"][0] == 2 and moves["Cc"][1] in (1, 2)
    top = {e["nickname"]: e for e in hs["leaderboard"]["top"]}
    assert top["Bb"]["delta_rank"] == -1
    ps = player_state(client, g, b)
    assert ps["leaderboard"]["me"]["rank"] == 3 and ps["leaderboard"]["me"]["above"]["score_gap"] > 0


def test_top_10_only(client, pack, monkeypatch):
    monkeypatch.setattr(live, "join_limiter", live.RateLimiter(1000, 10))
    g = new_game(client, pack)
    ps = [join(client, g, f"P{i:02d}") for i in range(12)]
    st = player_state(client, g, ps[-1])
    assert len(st["leaderboard"]["top"]) == 10 and st["leaderboard"]["me"]["rank"] == 1
    assert len(host_state(client, g)["leaderboard"]["top"]) == 10 and host_state(client, g)["players_count"] == 12


# ================================================================== player self-rename
def _age_rename(p, seconds=11):
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        c.execute("UPDATE live_player SET renamed_at = renamed_at - make_interval(secs => %s) WHERE id = %s",
                  (seconds, p["player_id"]))


def test_player_rename_any_time(client, pack):
    g = new_game(client, pack, n=2)
    a, b, k = join(client, g, "Ahmad"), join(client, g, "Beng"), join(client, g, "Rude")
    me = f"/api/live/games/{g['pin']}/me"
    st = client.patch(me, json={"nickname": "  Ahmad  Z "}, headers=a["P"])
    assert st.status_code == 200 and st.json()["me"]["nickname"] == "Ahmad Z"
    assert client.patch(me, json={"nickname": "Ahmad Z"}, headers=a["P"]).status_code == 200  # same name: no-op
    r = client.patch(me, json={"nickname": "Ahmad Y"}, headers=a["P"])
    assert r.status_code == 429  # 1 rename per 10 s
    _age_rename(a)
    assert client.patch(me, json={"nickname": "beng"}, headers=a["P"]).json()["detail"] == "name taken"
    for bad in ("", "x" * 21):
        assert client.patch(me, json={"nickname": bad}, headers=a["P"]).status_code == 422
    assert client.patch(me, json={"nickname": "Nope"}).status_code == 403
    # kicked names stay reserved; a kicked player can't rename
    client.post(f"/api/live/games/{g['pin']}/players/{k['player_id']}/kick", headers=g["H"])
    assert client.patch(me, json={"nickname": "rude"}, headers=a["P"]).status_code == 409
    assert client.patch(me, json={"nickname": "Nice"}, headers=k["P"]).status_code == 403
    # during a question, answers and score stay attached to the player id
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    ok = _correct_for(player_state(client, g, a)["question"]["prompt"])
    pts = answer_mc(client, g, a, ok).json()["result"]["points"]
    assert client.patch(me, json={"nickname": "Ahmad Star"}, headers=a["P"]).status_code == 200
    st = player_state(client, g, a)
    assert st["me"]["nickname"] == "Ahmad Star" and st["me"]["score"] == pts and st["me"]["answered_current"]
    assert host_state(client, g)["leaderboard"]["top"][0]["nickname"] == "Ahmad Star"
    # teacher locks renaming -> 403; the host can still rename
    client.patch(f"/api/live/games/{g['pin']}/settings", json={"allow_rename": False}, headers=g["H"])
    _age_rename(a)
    r = client.patch(me, json={"nickname": "Ahmad 2"}, headers=a["P"])
    assert r.status_code == 403 and r.json()["detail"] == "renaming locked by teacher"
    assert player_state(client, g, a)["settings"]["allow_rename"] is False
    hr = client.patch(f"/api/live/games/{g['pin']}/players/{a['player_id']}", json={"nickname": "Ahmad T"},
                      headers=g["H"])
    assert hr.status_code == 200
    client.patch(f"/api/live/games/{g['pin']}/settings", json={"allow_rename": True}, headers=g["H"])
    client.post(f"/api/live/games/{g['pin']}/end", headers=g["H"])
    assert client.patch(me, json={"nickname": "After"}, headers=b["P"]).status_code == 409  # ended


def test_rename_reaches_sse(client, server, pack, monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SEC", 1.0)
    g = new_game(client, pack)
    p = join(client, g, "Old Name")
    sink, stop, ready = [], threading.Event(), threading.Event()
    url = f"{server}/api/live/games/{g['pin']}/events?host_token={g['host_token']}"
    t = threading.Thread(target=_sse_reader, args=(url, sink, stop, ready), daemon=True)
    t.start()
    assert ready.wait(10) and _wait_for(lambda: any(e[0] == "state" for e in sink))
    client.patch(f"/api/live/games/{g['pin']}/me", json={"nickname": "New Name"}, headers=p["P"])
    assert _wait_for(lambda: any(e[0] == "state" and [x["nickname"] for x in e[1]["players"]] == ["New Name"]
                                 for e in sink))
    stop.set()
    t.join(5)


# ================================================================== 40-player burst (real server, threads)
def test_burst_40_players_consistent_scores_and_throttled_pushes(client, server, pack, monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SEC", 1.0)
    monkeypatch.setattr(live, "join_limiter", live.RateLimiter(1000, 10))
    g = new_game(client, pack, n=1)
    players = [join(client, g, f"Kid{i:02d}") for i in range(40)]
    events: list = []
    stop, ready = threading.Event(), threading.Event()

    def reader():
        url = f"{server}/api/live/games/{g['pin']}/events?host_token={g['host_token']}"
        try:
            with httpx.Client(timeout=httpx.Timeout(30, read=30)) as h, h.stream("GET", url) as r:
                ready.set()
                ev = None
                for line in r.iter_lines():
                    if line.startswith("event:"):
                        ev = line[6:].strip()
                    elif line.startswith("data:") and ev == "state":
                        events.append((time.monotonic(), json.loads(line[5:])))
                    if stop.is_set():
                        break
        except httpx.HTTPError:
            ready.set()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    assert ready.wait(10)
    client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"])
    ok = _correct_for(player_state(client, g, players[0])["question"]["prompt"])
    assert _wait_for(lambda: any(e[1]["status"] == "question" for e in events))
    t0 = time.monotonic()
    with httpx.Client(base_url=server, timeout=30, limits=httpx.Limits(max_connections=60)) as h:
        settings = f"/api/live/games/{g['pin']}/settings"

        def act(i):
            if i >= 40:  # 4 extra workers flip instant_feedback during the burst
                return [h.patch(settings, json={"instant_feedback": bool((i + k) % 2)}, headers=g["H"]).status_code
                        for k in range(3)]
            return h.post(f"/api/live/games/{g['pin']}/answer", json={"choice": ok if i % 3 else (ok + 1) % 2},
                          headers=players[i]["P"]).status_code

        res = _parallel(44, act)
    assert res[:40] == [200] * 40 and all(c == 200 for r in res[40:] for c in r)
    nxt(client, g)  # close the question: applies whatever is still pending (exactly once)
    burst_end = time.monotonic()
    assert _wait_for(lambda: any(e[1]["status"] == "reveal" for e in events))
    time.sleep(0.5)
    stop.set()

    # DB: every player's score == their single answer's points, every answer applied exactly once
    sc = _db_scores(g)
    pts = {r[0]: r[2] for r in stored_answers(g)}
    assert len(pts) == 40
    assert all(sc[p["player_id"]] == (pts[p["player_id"]], pts[p["player_id"]]) for p in players)
    assert sum(1 for v in pts.values() if v > 0) == len([i for i in range(40) if i % 3])
    final = [e[1] for e in events if e[1]["status"] == "reveal"][-1]
    assert sum(p["score"] for p in final["players"]) == sum(pts.values()) and final["answered_count"] == 40
    # SSE: bursts are coalesced to <= 5 pushes / s (+1 for window edges)
    ts = [e[0] for e in events if t0 - 0.1 <= e[0] <= burst_end + 0.5]
    worst = max(sum(1 for x in ts if s <= x < s + 1.0) for s in ts) if ts else 0
    assert worst <= 6, f"{worst} pushes in one second"
    assert len(events) < 40  # far fewer pushes than answers
