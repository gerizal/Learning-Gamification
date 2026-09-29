"""Integration tests for SELF-PACED / HOMEWORK mode (live_game.mode = 'self_paced', db/012_self_paced.sql).

Real dev PostgreSQL (DATABASE_URL) and a real uvicorn server in a background thread for SSE and the concurrency
tests. "Leaving" / waiting is simulated by shifting OUR OWN rows' timestamps in the DB.

Every row created here is tagged ("[pytest-sp]" titles / prompts, "pytest-sp-" pack slug) and deleted by primary
key at the end of the module (only rows this module created).
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:55432/playclass")
TAG = "[pytest-sp]"

psycopg = pytest.importorskip("psycopg")
httpx = pytest.importorskip("httpx")


def _db_reachable() -> str | None:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as c:
            c.execute("SELECT mode, closes_at, paused FROM live_game LIMIT 1")
            c.execute("SELECT current_idx, question_started_at, finished_at, question_order FROM live_player LIMIT 1")
        return None
    except Exception as exc:  # noqa: BLE001
        return f"DATABASE_URL unreachable or db/012_self_paced.sql not applied: {exc.__class__.__name__}"


_reason = _db_reachable()
if _reason:
    pytest.skip(_reason, allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import live, quiz, scoring  # noqa: E402
from app.main import app  # noqa: E402
from tests._seed import insert_pack, insert_question  # noqa: E402

CREATED: dict[str, set] = {"game": set(), "pack": set(), "question": set()}
MCQ = [  # prompt suffix, options, correct
    ("Homework one?", ["Alpha", "Bravo", "Charlie"], 0),
    ("Homework two?", ["Delta", "Echo"], 1),
    ("Homework three?", ["Foxtrot", "Golf", "Hotel", "India"], 2),
]
LIMIT = 20  # time_limit_sec of every test question
PACK_KEY = "pytest-sp-key-" + uuid.uuid4().hex


def _db():
    return psycopg.connect(os.environ["DATABASE_URL"])


# ------------------------------------------------------------------ cleanup (by PK, children first)
def _cleanup():
    games = [str(g) for g in CREATED["game"]]
    with _db() as c:
        if games:
            c.execute("DELETE FROM live_answer WHERE game_id = ANY(%s::uuid[])", (games,))
            c.execute("DELETE FROM live_player WHERE game_id = ANY(%s::uuid[])", (games,))
            c.execute("DELETE FROM live_question WHERE game_id = ANY(%s::uuid[])", (games,))
            c.execute("DELETE FROM live_game WHERE id = ANY(%s::uuid[])", (games,))
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        for qid in CREATED["question"]:
            try:
                c.execute("DELETE FROM question WHERE id = %s", (qid,))
            except psycopg.errors.ForeignKeyViolation:  # someone else's game picked it: archive ours instead
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


@pytest.fixture(scope="module")
def pack(client):
    # private (teacher-quiz-like): other users' "all packs" games can't pick our questions; plays in sort order
    p = insert_pack(slug=f"pytest-sp-{uuid.uuid4().hex[:8]}", name=f"{TAG} Pack", topic="general", description="d",
                    why_it_matters="w", edit_key_hash=quiz.hash_key(PACK_KEY))
    CREATED["pack"].add(p["id"])
    for i, (text, opts, correct) in enumerate(MCQ):
        q = insert_question(p["id"], prompt=f"{TAG} {text}", time_limit_sec=LIMIT, sort_order=i + 1, options=opts,
                            correct_option=correct)
        CREATED["question"].add(q["id"])
    return p


# ------------------------------------------------------------------ helpers
def correct_for(prompt: str) -> int:
    for text, _opts, correct in MCQ:
        if prompt == f"{TAG} {text}":
            return correct
    raise AssertionError(prompt)


def correct_text_for(prompt: str) -> str:
    for text, opts, correct in MCQ:
        if prompt == f"{TAG} {text}":
            return opts[correct]
    raise AssertionError(prompt)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def in_days(d: float) -> str:
    return iso(datetime.now(timezone.utc) + timedelta(days=d))


def new_hw(client, pack, n=3, **over):
    body = {"pack_id": pack["id"], "question_count": n, "title": f"{TAG} homework", "mode": "self_paced",
            "closes_at": in_days(7)}
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


def hstate(client, g):
    r = client.get(f"/api/live/games/{g['pin']}/state", params={"host_token": g["host_token"]})
    assert r.status_code == 200, r.text
    return r.json()


def pstate(client, g, p):
    r = client.get(f"/api/live/games/{g['pin']}/state", params={"player_token": p["player_token"]})
    assert r.status_code == 200, r.text
    return r.json()


def start(client, g, p):
    return client.post(f"/api/live/games/{g['pin']}/me/start", headers=p["P"])


def answer(client, g, p, choice, idx):
    return client.post(f"/api/live/games/{g['pin']}/answer", json={"choice": choice, "idx": idx}, headers=p["P"])


def settings(client, g, **body):
    return client.patch(f"/api/live/games/{g['pin']}/settings", json=body, headers=g["H"])


def play_one(client, g, p, right=True):
    """Start + answer the player's current question. Returns (start state, answer response json)."""
    r = start(client, g, p)
    assert r.status_code == 200, r.text
    st = r.json()
    ok = correct_for(st["question"]["prompt"])
    n = len(st["question"]["options"])
    a = answer(client, g, p, ok if right else (ok + 1) % n, st["me"]["current_idx"])
    assert a.status_code == 200, a.text
    return st, a.json()


def shift_start(p, seconds):
    """Pretend this player's current question was started `seconds` ago (our own test row only)."""
    with _db() as c:
        c.execute("UPDATE live_player SET question_started_at = question_started_at - make_interval(secs => %s) "
                  "WHERE id = %s AND question_started_at IS NOT NULL", (seconds, p["player_id"]))


def db_player(p):
    with _db() as c:
        return c.execute("SELECT score, streak, current_idx, question_started_at, finished_at, question_order "
                         "FROM live_player WHERE id = %s", (p["player_id"],)).fetchone()


def db_answers(g, p=None):
    with _db() as c:
        return c.execute("SELECT player_id, idx, points, answer_ms, passed, applied, feedback FROM live_answer "
                         "WHERE game_id = %s AND (%s::bigint IS NULL OR player_id = %s::bigint) ORDER BY id",
                         (g["game_id"], p and p["player_id"], p and p["player_id"])).fetchall()


def db_game(g):
    with _db() as c:
        return c.execute("SELECT status, closes_at, ended_at, paused, speed_bonus, instant_feedback, mode "
                         "FROM live_game WHERE id = %s", (g["game_id"],)).fetchone()


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
        t.join(60)
    return out


def _wait_for(pred, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


# ================================================================== create
def test_create_validation_and_defaults(client, pack):
    base = {"pack_id": pack["id"], "question_count": 3, "mode": "self_paced", "title": f"{TAG} v"}
    assert client.post("/api/live/games", json={**base, "closes_at": in_days(-0.01)}).status_code == 422
    assert client.post("/api/live/games", json={**base, "closes_at": in_days(30.01)}).status_code == 422
    assert client.post("/api/live/games", json={**base, "closes_at": "not a date"}).status_code == 422
    assert client.post("/api/live/games", json={**base, "mode": "dance"}).status_code == 422
    # closes_at / shuffle are self-paced only
    r = client.post("/api/live/games", json={"pack_id": pack["id"], "question_count": 3, "closes_at": in_days(1)})
    assert r.status_code == 422
    r = client.post("/api/live/games", json={"pack_id": pack["id"], "question_count": 3, "shuffle_per_player": True})
    assert r.status_code == 422

    g = new_hw(client, pack, closes_at=in_days(29.9), instant_feedback=False)
    assert g["mode"] == "self_paced" and g["total"] == 3 and g["closes_at"]
    row = db_game(g)
    assert row == ("open", row[1], None, False, False, True, "self_paced")  # speed off, instant forced on
    st = hstate(client, g)
    assert st["status"] == "open" and st["mode"] == "self_paced" and st["paused"] is False and st["closes_at"]
    assert st["settings"] == {"allow_rename": True, "instant_feedback": True, "speed_bonus": False,
                              "shuffle_per_player": False}
    assert st["progress"] == {"joined": 0, "in_progress": 0, "finished": 0} and st["players"] == []
    lk = client.get(f"/api/live/games/{g['pin']}").json()
    assert lk["joinable"] is True and lk["mode"] == "self_paced" and lk["paused"] is False
    # no deadline + naive timestamp (= UTC) are both fine; speed_bonus can be switched on
    g2 = new_hw(client, pack, closes_at=None, speed_bonus=True)
    assert g2["closes_at"] is None and db_game(g2)[4] is True
    naive = (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    g3 = new_hw(client, pack, closes_at=naive)
    assert abs(datetime.fromisoformat(g3["closes_at"]) - datetime.fromisoformat(naive + "+00:00")) < timedelta(seconds=1)
    # host phase controls don't exist here
    assert client.post(f"/api/live/games/{g['pin']}/start", headers=g["H"]).status_code == 409
    assert client.post(f"/api/live/games/{g['pin']}/next", headers=g["H"]).status_code == 409
    # live games are untouched: lobby, speed bonus on, no mode-only keys in create
    r = client.post("/api/live/games", json={"pack_id": pack["id"], "question_count": 1, "title": f"{TAG} live"})
    CREATED["game"].add(r.json()["game_id"])
    assert r.status_code == 201 and "closes_at" not in r.json()
    with _db() as c:
        assert c.execute("SELECT mode, status, speed_bonus FROM live_game WHERE id = %s",
                         (r.json()["game_id"],)).fetchone() == ("live", "lobby", True)
    assert client.post(f"/api/live/games/{r.json()['pin']}/me/start",
                       headers={"X-Player-Token": "x"}).status_code == 403


# ================================================================== the player flow
def test_full_play_through_with_resume(client, pack):
    g = new_hw(client, pack)
    p = join(client, g, "Walker")
    st = pstate(client, g, p)
    assert st["mode"] == "self_paced" and st["status"] == "open" and st["question"] is None
    assert st["me"]["current_idx"] == 0 and st["me"]["total"] == 3 and st["me"]["question_started_at"] is None
    assert st["me"]["finished_at"] is None and st["server_now"] and st["time_left_ms"] is None
    assert answer(client, g, p, 0, 0).status_code == 409  # not started yet

    # Q0: start (question shown, no answer), answer right -> result + advance
    r = start(client, g, p)
    assert r.status_code == 200
    s0 = r.json()
    assert s0["question"]["idx"] == 0 and s0["question"]["prompt"] == f"{TAG} {MCQ[0][0]}"
    assert "correct" not in json.dumps(s0) and "correct_option" not in json.dumps(s0)
    assert s0["me"]["question_started_at"] and 0 < s0["time_left_ms"] <= LIMIT * 1000
    a = answer(client, g, p, MCQ[0][2], 0).json()
    assert a["accepted"] and a["result"]["passed"] and a["result"]["correct"]["option"] == MCQ[0][2]
    assert a["current_idx"] == 1 and a["total"] == 3 and a["finished"] is False
    st = pstate(client, g, p)
    assert st["me"]["current_idx"] == 1 and st["me"]["score"] == a["result"]["points"] == 100
    assert st["me"]["last_result"]["correct"]["option"] == MCQ[0][2] and st["question"] is None

    # "leave" between questions for 3 days: the unstarted question does not expire
    with _db() as c:
        c.execute("UPDATE live_player SET joined_at = joined_at - interval '3 days' WHERE id = %s", (p["player_id"],))
    st = pstate(client, g, p)
    assert st["me"]["current_idx"] == 1 and st["question"] is None

    # Q1: start, "close the tab" for 8 s, come back: same question, same clock, less time left
    s1 = start(client, g, p).json()
    shift_start(p, 8)
    back = pstate(client, g, p)
    assert back["question"]["idx"] == 1 and back["time_left_ms"] <= (LIMIT - 8) * 1000
    again = start(client, g, p).json()  # idempotent: never resets the clock
    assert again["me"]["question_started_at"] == back["me"]["question_started_at"] != s1["me"]["question_started_at"]
    a = answer(client, g, p, (MCQ[1][2] + 1) % 2, 1).json()  # wrong
    assert a["result"]["passed"] is False and a["result"]["points"] == 0 and a["result"]["streak"] == 0

    # Q2 (last): finishes the game for this player
    _s, a = play_one(client, g, p)
    assert a["finished"] is True and a["current_idx"] == 3
    st = pstate(client, g, p)
    assert st["me"]["finished_at"] and st["me"]["current_idx"] == 3 and st["question"] is None
    assert st["me"]["last_result"]["correct"]["option"] == MCQ[2][2]
    assert start(client, g, p).status_code == 409
    assert answer(client, g, p, 0, 3).status_code == 409
    rows = db_answers(g, p)
    assert [r[1] for r in rows] == [0, 1, 2] and all(r[5] for r in rows)  # applied at once, real idx
    assert db_player(p)[0] == sum(r[2] for r in rows) == 200


def test_expired_started_question_is_no_answer_and_advances(client, pack):
    g = new_hw(client, pack)
    p = join(client, g, "Sleepy")
    play_one(client, g, p)  # Q0 right -> streak 1
    assert db_player(p)[1] == 1
    start(client, g, p)
    shift_start(p, LIMIT + 3 + 1)  # past time limit + 3 s grace
    st = pstate(client, g, p)  # lazy: recorded as no answer on this read
    assert st["me"]["current_idx"] == 2 and st["question"] is None and st["me"]["last_result"] is None
    assert db_player(p)[:3] == (100, 1, 2)  # 0 points, streak unchanged
    assert [r[1] for r in db_answers(g, p)] == [0]  # no row for the timed-out question
    # the late answer for the expired question is refused (its idx is no longer current)
    assert answer(client, g, p, 0, 1).status_code == 409
    # expiry through /answer itself: 409 "Time is up" and the advance is kept (committed)
    start(client, g, p)
    shift_start(p, LIMIT + 3 + 1)
    r = answer(client, g, p, MCQ[2][2], 2)
    assert r.status_code == 409 and r.json()["detail"] == "Time is up"
    pl = db_player(p)
    assert pl[2] == 3 and pl[4] is not None and pl[3] is None  # finished (timed out on the last one)
    # within the grace period it is still accepted
    g2 = new_hw(client, pack, n=1)
    p2 = join(client, g2, "Grace")
    start(client, g2, p2)
    shift_start(p2, LIMIT + 2)
    r = answer(client, g2, p2, MCQ[0][2], 0)
    assert r.status_code == 200 and r.json()["result"]["passed"]


def test_expiry_through_start_then_next_question(client, pack):
    g = new_hw(client, pack)
    p = join(client, g, "Returner")
    start(client, g, p)
    shift_start(p, 3600)
    r = start(client, g, p)  # expired Q0 is recorded, the player starts Q1 at once
    assert r.status_code == 200 and r.json()["me"]["current_idx"] == 1 and r.json()["question"]["idx"] == 1
    assert db_answers(g, p) == []


def test_unstarted_question_never_expires(client, pack):
    g = new_hw(client, pack)
    p = join(client, g, "Idle")
    with _db() as c:
        c.execute("UPDATE live_player SET joined_at = joined_at - interval '20 days' WHERE id = %s",
                  (p["player_id"],))
    for _ in range(2):
        st = pstate(client, g, p)
        assert st["me"]["current_idx"] == 0 and st["me"]["question_started_at"] is None
    r = start(client, g, p)
    assert r.status_code == 200 and r.json()["me"]["current_idx"] == 0 and r.json()["time_left_ms"] > (LIMIT - 2) * 1000


def test_wrong_or_missing_idx(client, pack):
    g = new_hw(client, pack)
    p = join(client, g, "Idx")
    start(client, g, p)
    assert answer(client, g, p, 0, 1).status_code == 409
    assert answer(client, g, p, 0, -1).status_code == 409
    r = client.post(f"/api/live/games/{g['pin']}/answer", json={"choice": 0}, headers=p["P"])
    assert r.status_code == 422
    assert answer(client, g, p, 7, 0).status_code == 422  # choice out of range
    assert db_answers(g) == [] and db_player(p)[2] == 0
    assert answer(client, g, p, MCQ[0][2], 0).status_code == 200
    assert answer(client, g, p, MCQ[0][2], 0).status_code == 409  # same idx again: moved on


# ================================================================== teacher control
def test_pause_blocks_join_start_answer(client, pack):
    g = new_hw(client, pack)
    a = join(client, g, "Paula")
    b = join(client, g, "Pete")
    start(client, g, a)
    st = settings(client, g, paused=True)
    assert st.status_code == 200 and st.json()["paused"] is True
    assert settings(client, g, paused=True).status_code == 200  # no-op
    r = client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": "Late"})
    assert r.status_code == 409 and "paused" in r.json()["detail"]
    assert start(client, g, b).status_code == 409
    r = answer(client, g, a, MCQ[0][2], 0)
    assert r.status_code == 409 and "paused" in r.json()["detail"]
    assert client.get(f"/api/live/games/{g['pin']}").json()["joinable"] is False
    ps = pstate(client, g, a)  # state reads still work
    assert ps["paused"] is True and ps["question"]["idx"] == 0
    assert db_answers(g) == []
    # the in-flight clock is NOT extended by a pause
    shift_start(a, LIMIT + 4)
    assert settings(client, g, paused=False).json()["paused"] is False
    assert answer(client, g, a, MCQ[0][2], 0).status_code == 409  # time is up
    assert db_player(a)[2] == 1
    assert start(client, g, b).status_code == 200
    join(client, g, "Late")
    assert settings(client, g, paused=None).status_code == 422
    # live games have no pause / deadline
    r = client.post("/api/live/games", json={"pack_id": pack["id"], "question_count": 1, "title": f"{TAG} live"})
    lg = r.json()
    CREATED["game"].add(lg["game_id"])
    assert client.patch(f"/api/live/games/{lg['pin']}/settings", json={"paused": True},
                        headers={"X-Host-Token": lg["host_token"]}).status_code == 422
    assert client.patch(f"/api/live/games/{g['pin']}/settings", json={"paused": True}).status_code == 403


def test_extend_shorten_and_clear_deadline(client, pack):
    g = new_hw(client, pack, closes_at=in_days(1))
    p = join(client, g, "Dora")
    r = settings(client, g, closes_at=in_days(20))
    assert r.status_code == 200
    assert datetime.fromisoformat(r.json()["closes_at"]) > datetime.now(timezone.utc) + timedelta(days=19)
    assert settings(client, g, closes_at=in_days(31)).status_code == 422
    r = settings(client, g, closes_at=None)  # no deadline
    assert r.status_code == 200 and r.json()["closes_at"] is None and db_game(g)[1] is None
    r = settings(client, g, closes_at=in_days(0.5))  # shorten
    assert r.status_code == 200 and r.json()["status"] == "open"
    assert start(client, g, p).status_code == 200
    r = settings(client, g, closes_at=iso(datetime.now(timezone.utc) - timedelta(minutes=1)))  # into the past
    assert r.status_code == 200 and r.json()["status"] == "ended"
    row = db_game(g)
    assert row[0] == "ended" and row[2] is not None
    assert answer(client, g, p, 0, 0).status_code == 409
    assert settings(client, g, closes_at=in_days(3)).status_code == 409  # ended is final
    assert settings(client, g, allow_rename=False).status_code == 200  # other settings still fine


def test_auto_close_after_deadline(client, pack):
    g = new_hw(client, pack, closes_at=in_days(1))
    p = join(client, g, "Late Larry")
    start(client, g, p)
    with _db() as c:  # the deadline passed a minute ago (our own row)
        c.execute("UPDATE live_game SET closes_at = clock_timestamp() - interval '1 minute' WHERE id = %s",
                  (g["game_id"],))
    assert db_game(g)[0] == "open"  # lazy: nothing happens without a read
    st = pstate(client, g, p)
    assert st["status"] == "ended" and st["question"] is None
    status, closes_at, ended_at, *_ = db_game(g)
    assert status == "ended" and ended_at == closes_at
    assert answer(client, g, p, 0, 0).status_code == 409
    assert start(client, g, p).status_code == 409
    assert client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": "Later"}).status_code == 409
    assert hstate(client, g)["status"] == "ended"
    # the join path auto-closes too (first read after the deadline is a join)
    g2 = new_hw(client, pack, closes_at=in_days(1))
    with _db() as c:
        c.execute("UPDATE live_game SET closes_at = clock_timestamp() - interval '1 second' WHERE id = %s",
                  (g2["game_id"],))
    assert client.post(f"/api/live/games/{g2['pin']}/join", json={"nickname": "X"}).status_code == 409
    assert client.get(f"/api/live/games/{g2['pin']}").json()["status"] == "ended"
    assert db_game(g2)[0] == "ended"


def test_end(client, pack):
    g = new_hw(client, pack)
    p = join(client, g, "Ender")
    play_one(client, g, p)
    start(client, g, p)
    r = client.post(f"/api/live/games/{g['pin']}/end", headers=g["H"])
    assert r.status_code == 200 and r.json()["status"] == "ended" and r.json()["mode"] == "self_paced"
    assert client.post(f"/api/live/games/{g['pin']}/end", headers=g["H"]).status_code == 200  # idempotent
    assert answer(client, g, p, 0, 1).status_code == 409
    assert start(client, g, p).status_code == 409
    assert client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": "N"}).status_code == 409
    st = pstate(client, g, p)
    assert st["status"] == "ended" and st["me"]["score"] == 100 and st["question"] is None
    assert db_game(g)[2] is not None


def test_kick_and_rename(client, pack):
    g = new_hw(client, pack)
    a = join(client, g, "Troll")
    b = join(client, g, "Bea")
    start(client, g, a)
    r = client.patch(f"/api/live/games/{g['pin']}/players/{b['player_id']}", json={"nickname": "Beatrice"},
                     headers=g["H"])
    assert r.status_code == 200 and [x["nickname"] for x in r.json()["players"]] == ["Troll", "Beatrice"]
    r = client.post(f"/api/live/games/{g['pin']}/players/{a['player_id']}/kick", headers=g["H"])
    assert r.status_code == 200 and [x["nickname"] for x in r.json()["players"]] == ["Beatrice"]
    assert r.json()["progress"]["joined"] == 1
    assert client.get(f"/api/live/games/{g['pin']}/state", params={"player_token": a["player_token"]}).status_code == 403
    assert start(client, g, a).status_code == 403
    assert answer(client, g, a, 0, 0).status_code == 403
    assert client.post(f"/api/live/games/{g['pin']}/join", json={"nickname": "troll"}).status_code == 409
    # player self-rename works like live
    r = client.patch(f"/api/live/games/{g['pin']}/me", json={"nickname": "Bee"}, headers=b["P"])
    assert r.status_code == 200 and r.json()["me"]["nickname"] == "Bee" and r.json()["mode"] == "self_paced"


def test_shuffle_per_player_stable_order(client, pack):
    g = new_hw(client, pack, shuffle_per_player=True)
    players = [join(client, g, f"Shuf{i}") for i in range(8)]
    orders = [db_player(p)[5] for p in players]
    assert all(sorted(o) == [0, 1, 2] for o in orders)
    assert len({tuple(o) for o in orders}) > 1  # 8 random permutations of 3 all equal: p = 6^-7
    prompts = {i: f"{TAG} {MCQ[i][0]}" for i in range(3)}
    for p, order in zip(players[:3], orders[:3]):
        for pos in range(3):
            st = start(client, g, p).json()
            assert st["question"]["idx"] == pos and st["question"]["prompt"] == prompts[order[pos]]
            assert pstate(client, g, p)["question"]["prompt"] == prompts[order[pos]]  # stable across reads
            assert answer(client, g, p, correct_for(st["question"]["prompt"]), pos).status_code == 200
        assert [r[1] for r in db_answers(g, p)] == order  # stored at the real question idx
        assert db_player(p)[5] == order  # never re-shuffled
    # not shuffled by default: everybody gets the teacher's order
    g2 = new_hw(client, pack)
    q = join(client, g2, "Plain")
    assert db_player(q)[5] is None and start(client, g2, q).json()["question"]["prompt"] == prompts[0]


def test_speed_bonus_off_vs_on(client, pack):
    """Homework default: speed factor 1.0 whatever the time. speed_bonus: live formula on the server clock."""
    results = {}
    for sb in (False, True):
        g = new_hw(client, pack, n=1, speed_bonus=sb)
        p = join(client, g, f"Speed{sb}")
        start(client, g, p)
        shift_start(p, LIMIT / 2)  # answered after half the time
        a = answer(client, g, p, MCQ[0][2], 0).json()["result"]
        (_pid, _idx, points, answer_ms, passed, applied, fb), = db_answers(g, p)
        assert passed and applied and LIMIT / 2 * 1000 <= answer_ms < LIMIT / 2 * 1000 + 3000
        expect = scoring.live_points(base_points=100, difficulty=1, accuracy=100, passed=True,
                                     answer_ms=answer_ms if sb else 0, time_limit_sec=LIMIT, streak=1)
        assert points == a["points"] == expect["points"] and a["speed_factor"] == expect["speed_factor"]
        results[sb] = (points, a["speed_factor"])
    assert results[False] == (100, 1.0)
    assert 70 <= results[True][0] <= 75 and 0.7 <= results[True][1] <= 0.75  # 100 * (1 - 0.5 * ~0.5)


# ================================================================== concurrency (real server, threads)
def test_double_start_and_double_answer(client, server, pack):
    g = new_hw(client, pack)
    p = join(client, g, "Twin")
    with httpx.Client(base_url=server, timeout=20) as h:
        res = _parallel(2, lambda i: h.post(f"/api/live/games/{g['pin']}/me/start", headers=p["P"]))
        assert [r.status_code for r in res] == [200, 200]
        s0, s1 = (r.json()["me"]["question_started_at"] for r in res)
        assert s0 == s1 and s0 is not None
        started = db_player(p)[3]
        res = _parallel(2, lambda i: h.post(f"/api/live/games/{g['pin']}/answer",
                                            json={"choice": i, "idx": 0}, headers=p["P"]))
    assert sorted(r.status_code for r in res) == [200, 409]
    assert len(db_answers(g, p)) == 1
    pl = db_player(p)
    assert pl[2] == 1 and pl[3] is None and started is not None  # advanced exactly once


def test_30_player_homework_burst(client, server, pack, monkeypatch):
    monkeypatch.setattr(live, "join_limiter", live.RateLimiter(1000, 10))
    g = new_hw(client, pack, shuffle_per_player=True)
    players = [join(client, g, f"Kid{i:02d}") for i in range(30)]
    with httpx.Client(base_url=server, timeout=60, limits=httpx.Limits(max_connections=40)) as h:
        def run(i):
            p, codes = players[i], []
            for pos in range(3):
                r = h.post(f"/api/live/games/{g['pin']}/me/start", headers=p["P"])
                codes.append(r.status_code)
                q = r.json()["question"]
                ok = correct_for(q["prompt"])
                choice = ok if (i + pos) % 3 else (ok + 1) % len(q["options"])
                r = h.post(f"/api/live/games/{g['pin']}/answer", json={"choice": choice, "idx": pos}, headers=p["P"])
                codes.append(r.status_code)
            return codes

        res = _parallel(30, run)
    assert all(c == [200] * 6 for c in res), res
    with _db() as c:
        rows = c.execute(
            """SELECT p.id, p.score, p.current_idx, p.finished_at IS NOT NULL, p.question_started_at IS NULL,
                      COALESCE(SUM(a.points), 0)::int, COUNT(a.id)::int, bool_and(a.applied),
                      COUNT(a.id) FILTER (WHERE a.passed)::int, p.streak
                 FROM live_player p LEFT JOIN live_answer a ON a.player_id = p.id
                WHERE p.game_id = %s GROUP BY p.id""", (g["game_id"],)).fetchall()
    assert len(rows) == 30
    for pid, score, cur, fin, idle, pts, n, applied, passed, streak in rows:
        assert (cur, fin, idle, n, applied) == (3, True, True, 3, True)
        assert score == pts
    hs = hstate(client, g)
    assert hs["progress"] == {"joined": 30, "in_progress": 0, "finished": 30}
    assert sum(p["score"] for p in hs["players"]) == sum(r[1] for r in rows)
    assert sum(q["answered"] for q in hs["per_question"]) == 90


# ================================================================== host monitor
def test_host_monitor_progress_and_per_question(client, pack):
    g = new_hw(client, pack)
    done, mid, fresh = join(client, g, "Done"), join(client, g, "Mid"), join(client, g, "Fresh")
    for right in (True, False, True):
        play_one(client, g, done, right)
    play_one(client, g, mid, True)
    start(client, g, mid)
    st = hstate(client, g)
    assert st["progress"] == {"joined": 3, "in_progress": 1, "finished": 1}
    assert [set(p) for p in st["players"]] == [{"id", "nickname", "score", "current_idx", "total", "finished_at",
                                                 "last_active_at"}] * 3
    by = {p["nickname"]: p for p in st["players"]}
    assert (by["Done"]["current_idx"], by["Mid"]["current_idx"], by["Fresh"]["current_idx"]) == (3, 1, 0)
    assert by["Done"]["finished_at"] and by["Mid"]["finished_at"] is None and by["Done"]["total"] == 3
    assert by["Mid"]["last_active_at"] > by["Fresh"]["last_active_at"]  # started a question after joining
    assert st["per_question"] == [
        {"idx": 0, "prompt": f"{TAG} {MCQ[0][0]}", "answered": 2, "correct_pct": 100.0},
        {"idx": 1, "prompt": f"{TAG} {MCQ[1][0]}", "answered": 1, "correct_pct": 0.0},
        {"idx": 2, "prompt": f"{TAG} {MCQ[2][0]}", "answered": 1, "correct_pct": 100.0}]
    assert st["leaderboard"]["top"][0]["nickname"] == "Done" and st["summary"] == {"joined": 3, "answered_any": 2}
    assert st["reveal"] is None and '"correct"' not in json.dumps(st) and "option_text" not in json.dumps(st)
    # player state has its own progress + the leaderboard, never others' progress
    ps = pstate(client, g, fresh)
    assert "players" not in ps and "per_question" not in ps and "progress" not in ps
    assert ps["leaderboard"]["me"]["rank"] == 3 and ps["leaderboard"]["me"]["above"]["nickname"] == "Mid"


def test_sse_host_monitor_updates_after_answer(client, server, pack, monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SEC", 1.0)
    g = new_hw(client, pack)
    p = join(client, g, "Streamy")
    sink, stop, ready = [], threading.Event(), threading.Event()

    def reader(url, out):
        try:
            with httpx.Client(timeout=httpx.Timeout(20, read=20)) as h, h.stream("GET", url) as r:
                ready.set()
                ev = None
                for line in r.iter_lines():
                    if line.startswith("event:"):
                        ev = line[6:].strip()
                    elif line.startswith("data:") and ev:
                        out.append((ev, json.loads(line[5:])))
                    if stop.is_set():
                        break
        except Exception as exc:  # noqa: BLE001
            out.append(("error", repr(exc)))
            ready.set()

    t = threading.Thread(target=reader, daemon=True,
                         args=(f"{server}/api/live/games/{g['pin']}/events?host_token={g['host_token']}", sink))
    t.start()
    assert ready.wait(10) and _wait_for(lambda: any(e[0] == "state" for e in sink))
    first = next(e[1] for e in sink if e[0] == "state")
    assert first["mode"] == "self_paced" and first["players"][0]["current_idx"] == 0
    # answer through the OTHER app instance (TestClient) -> reaches this stream via LISTEN/NOTIFY
    play_one(client, g, p)
    assert _wait_for(lambda: any(e[0] == "state" and e[1]["players"][0]["current_idx"] == 1
                                 and e[1]["per_question"][0]["answered"] == 1 for e in sink))
    # deadline passing while the monitor watches -> the stream re-reads, the game auto-closes
    with _db() as c:
        c.execute("UPDATE live_game SET closes_at = clock_timestamp() + interval '1 second' WHERE id = %s",
                  (g["game_id"],))
    settings(client, g, allow_rename=False)  # any change so the stream sees the new closes_at
    assert _wait_for(lambda: any(e[0] == "state" and e[1]["status"] == "ended" for e in sink), timeout=8)
    assert not any(e[0] == "error" for e in sink), sink
    stop.set()
    t.join(5)


# ================================================================== CSV + leaks
def test_csv_has_progress_and_finished_at(client, pack):
    g = new_hw(client, pack)
    a, b = join(client, g, "Csv A"), join(client, g, "Csv B")
    for _ in range(3):
        play_one(client, g, a)
    play_one(client, g, b, right=False)
    r = client.get(f"/api/live/games/{g['pin']}/report.csv", params={"host_token": g["host_token"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "homework-" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert list(rows[0].keys()) == live.CSV_COLS + ["progress", "finished_at"]
    by = {x["nickname"]: x for x in rows}
    assert by["Csv A"]["progress"] == "3/3" and datetime.fromisoformat(by["Csv A"]["finished_at"])
    assert by["Csv A"]["answered"] == "3" and by["Csv A"]["correct"] == "3" and by["Csv A"]["rank"] == "1"
    assert by["Csv B"]["progress"] == "1/3" and by["Csv B"]["finished_at"] == ""
    assert by["Csv B"]["score"] == "0" and by["Csv B"]["avg_accuracy"] == "0.00"


def test_no_correct_option_before_answering(client, server, pack, monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SEC", 1.0)
    g = new_hw(client, pack)
    ahead, behind = join(client, g, "Ahead"), join(client, g, "Behind")
    for _ in range(2):
        play_one(client, g, ahead)  # Ahead has answered Q0 and Q1 -> sees ONLY their own last result
    sink, stop, ready = [], threading.Event(), threading.Event()

    def reader():
        url = f"{server}/api/live/games/{g['pin']}/events?player_token={behind['player_token']}"
        with httpx.Client(timeout=httpx.Timeout(20, read=20)) as h, h.stream("GET", url) as r:
            ready.set()
            ev = None
            for line in r.iter_lines():
                if line.startswith("event:"):
                    ev = line[6:].strip()
                elif line.startswith("data:") and ev:
                    sink.append((ev, json.loads(line[5:])))
                if stop.is_set():
                    break

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    assert ready.wait(10) and _wait_for(lambda: any(e[0] == "state" for e in sink))

    # Behind (who hasn't answered anything) never gets a correct answer: state, start, SSE, lookup
    views = [pstate(client, g, behind)]
    views.append(start(client, g, behind).json())
    views.append(pstate(client, g, behind))
    play_one(client, g, ahead)  # Ahead finishes while Behind is on Q0 -> Behind's stream gets a push
    assert _wait_for(lambda: sum(1 for e in sink if e[0] == "state") >= 2)
    views += [e[1] for e in sink if e[0] == "state"]
    views.append(client.get(f"/api/live/games/{g['pin']}").json())
    for v in views:
        text = json.dumps(v)
        assert '"correct"' not in text and "correct_option" not in text and "option_text" not in text, v
        assert v.get("reveal") is None
        if v.get("me"):
            assert v["me"]["last_result"] is None
    q0 = next(v for v in views if v.get("question"))["question"]
    assert set(q0) >= {"idx", "prompt", "options", "time_limit_sec"} and q0["idx"] == 0

    # Behind answers Q0 -> now (and only now) sees Q0's correct answer, not Q1's
    a = answer(client, g, behind, 0, 0).json()
    assert a["result"]["correct"] == {"option": MCQ[0][2], "option_text": MCQ[0][1][MCQ[0][2]]}
    st = start(client, g, behind).json()
    text = json.dumps({k: v for k, v in st.items() if k != "me"}) + json.dumps(
        {k: v for k, v in st["me"].items() if k != "last_result"})
    assert '"correct"' not in text and "option_text" not in text
    assert st["me"]["last_result"]["correct"]["option"] == MCQ[0][2]
    # the host monitor never carries correct options either
    assert '"correct"' not in json.dumps(hstate(client, g)) and "option_text" not in json.dumps(hstate(client, g))
    stop.set()
    t.join(5)
