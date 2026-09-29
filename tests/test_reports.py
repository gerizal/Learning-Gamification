"""Program-team reports (/api/reports, app/reports.py) — CONTRACT.md "REPORTS".

Real dev PostgreSQL. Fixture data is inserted with SQL (every text tagged "[pytest-reports <run>]", sessions dated in
a random per-run year so nobody else's data — not even a concurrent run of this file — falls in the same filters), and every row is deleted by primary key at the end.
Expected numbers are hand-computed in the comments next to the seed.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import random
import uuid
from datetime import date

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost:55432/playclass")
psycopg = pytest.importorskip("psycopg")

# Per-run tag and year: concurrent runs of this file on the shared DB never see each other's rows.
RUN = os.environ.get("REPORTS_TEST_RUN") or uuid.uuid4().hex[:6]
TAG = os.environ.get("REPORTS_TEST_TAG") or f"[pytest-reports {RUN}]"
Y = os.environ.get("REPORTS_TEST_YEAR") or str(random.randint(1100, 1999))
SCHOOL_A = f"{TAG} School A"
SCHOOL_B = f"{TAG} School B"
P1 = f"{TAG} Legacy program"  # the app no longer collects program; only G1 carries one
KEY = {"X-Reports-Key": os.environ["REPORTS_KEY"]}  # set by tests/conftest.py (the app has no default)
TZ = "+07"  # timestamps are written with an explicit offset; dates are read in the DB timezone


def _db_reachable() -> str | None:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as c:
            c.execute("SELECT mode, finished_at FROM live_game g JOIN live_player p ON p.game_id = g.id LIMIT 1")
        return None
    except Exception as exc:  # noqa: BLE001
        return f"DATABASE_URL unreachable or db/006..012 not applied: {exc.__class__.__name__}"


_reason = _db_reachable()
if _reason:
    pytest.skip(_reason, allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import reports  # noqa: E402

SLUG = reports._slug(TAG)
from app.main import app  # noqa: E402

PK: dict[str, list] = {k: [] for k in ("pack", "question", "game", "lq", "player", "answer", "classroom", "student",
                                        "session", "team", "turn", "attendance", "attempt")}


# ------------------------------------------------------------------ seed (SQL, tagged) + cleanup by PK
def _ts(day: str, hm: str) -> str:
    return f"{day} {hm}:00{TZ}"


def _seed(c) -> dict:
    ids: dict = {}
    pack = c.execute("INSERT INTO question_pack (slug, name, topic, edit_key_hash) VALUES (%s, %s, 'general', %s) "
                     "RETURNING id", (f"pytest-reports-{uuid.uuid4().hex[:10]}", f"{TAG} pack",
                                      uuid.uuid4().hex)).fetchone()[0]
    PK["pack"].append(pack)
    q = c.execute("INSERT INTO question (game_mode, prompt, options, correct_option, pack_id) "
                  "VALUES ('multiple_choice', %s, '{a,b}', 0, %s) RETURNING id", (f"{TAG} q", pack)).fetchone()[0]
    PK["question"].append(q)

    def game(name, school, program, day, status, cur_idx, nq, mode="live"):
        for _ in range(50):
            pin = str(random.randint(100000, 999999))
            try:
                with c.transaction():
                    gid = c.execute(
                        """INSERT INTO live_game (pin, host_token, title, teacher_name, school, program, status,
                                                  current_index, created_at, mode)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (pin, uuid.uuid4().hex, f"{TAG} {name}", "T. Teacher", school, program, status, cur_idx,
                         _ts(day, "10:00"), mode)).fetchone()[0]
                break
            except psycopg.errors.UniqueViolation:
                continue
        PK["game"].append(gid)
        for i in range(nq):
            c.execute("INSERT INTO live_question (game_id, idx, question_id) VALUES (%s, %s, %s)", (gid, i, q))
            PK["lq"].append((gid, i))
        ids[name] = gid
        return gid

    def player(gid, nick, score, joined, kicked=False, finished=None, cur_idx=0):
        pid = c.execute("""INSERT INTO live_player (game_id, nickname, player_token, score, is_kicked, joined_at,
                                                    finished_at, current_idx)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (gid, nick, uuid.uuid4().hex, score, kicked, joined, finished, cur_idx)).fetchone()[0]
        PK["player"].append(pid)
        return pid

    def answer(gid, pid, idx, acc, at):
        aid = c.execute("""INSERT INTO live_answer (game_id, idx, player_id, accuracy, passed, stars, points, answer_ms,
                                                    applied, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, 0, 1000, true, %s) RETURNING id""",
                        (gid, idx, pid, acc, acc >= 60, 3 if acc >= 90 else 0, at)).fetchone()[0]
        PK["answer"].append(aid)

    d1 = f"{Y}-03-01"
    # G1 — School A (legacy program value P1), 2001-03-01, ended at question index 2 → 3 questions played.
    g1 = game("G1", SCHOOL_A, P1, d1, "ended", 2, 3)
    aisyah = player(g1, "Aisyah", 1800, _ts(d1, "10:00"))
    ben = player(g1, "Ben", 0, _ts(d1, "10:00"))
    player(g1, "Chen", 0, _ts(d1, "10:00"))                                  # joined, never answered
    dina = player(g1, "Dina", 1500, _ts(d1, "10:10"))                         # late joiner
    kid = player(g1, "Kicked Kid", 900, _ts(d1, "10:00"), kicked=True)       # excluded everywhere
    answer(g1, aisyah, 0, 100, _ts(d1, "10:01"))
    answer(g1, ben, 0, 0, _ts(d1, "10:02"))
    answer(g1, kid, 0, 100, _ts(d1, "10:03"))
    answer(g1, aisyah, 1, 100, _ts(d1, "10:05"))
    answer(g1, dina, 1, 100, _ts(d1, "10:11"))
    answer(g1, aisyah, 2, 0, _ts(d1, "10:12"))
    answer(g1, dina, 2, 100, _ts(d1, "10:12"))
    # Dina joined 10:10: question 1 had its first answer at 10:05 (< join) → question 0 had closed → present for 2.
    # G1: participants 4, participated 3, completed Aisyah (3/3) + Dina (2/2) = 2, avg = 400/6 = 66.67

    d2 = f"{Y}-03-15"
    # G2 — "school a " (other spelling, same school), 2 questions.
    g2 = game("G2", f"{TAG} school a ", "", d2, "ended", 1, 2)
    a2 = player(g2, "AISYAH", 2000, _ts(d2, "10:00"))
    b2 = player(g2, "Ben", 800, _ts(d2, "10:00"))
    answer(g2, a2, 0, 100, _ts(d2, "10:01"))
    answer(g2, a2, 1, 100, _ts(d2, "10:03"))
    answer(g2, b2, 0, 100, _ts(d2, "10:01"))
    answer(g2, b2, 1, 0, _ts(d2, "10:03"))
    # G2: participants 2, participated 2, completed 2, avg 300/4 = 75

    # G3 — blank school ("(not set)"), never started (ended from the lobby: 0 questions played).
    g3 = game("G3", "  ", "", f"{Y}-04-01", "ended", -1, 3)
    player(g3, "Zed", 0, _ts(f"{Y}-04-01", "10:00"))

    # G4 — School A, 1 question.
    g4 = game("G4", SCHOOL_A, "", f"{Y}-05-01", "ended", 0, 1)
    a4 = player(g4, "Aisyah", 1000, _ts(f"{Y}-05-01", "10:00"))
    answer(g4, a4, 0, 100, _ts(f"{Y}-05-01", "10:01"))

    # G5 — HOMEWORK (self_paced, open), School B, 2 questions; Siti finished, Omar half way.
    d5 = f"{Y}-04-10"
    g5 = game("G5", SCHOOL_B, "", d5, "open", -1, 2, mode="self_paced")
    # deadline passed but nobody read it since (closing is lazy): stored 'open', effective status 'ended'
    c.execute("UPDATE live_game SET closes_at = %s WHERE id = %s", (_ts(d5, "20:00"), g5))
    siti_hw = player(g5, "Siti", 1600, _ts(d5, "10:00"), finished=_ts(d5, "18:00"), cur_idx=2)
    omar = player(g5, "Omar", 0, _ts(d5, "11:00"), cur_idx=1)
    answer(g5, siti_hw, 0, 100, _ts(d5, "17:00"))
    answer(g5, siti_hw, 1, 100, _ts(d5, "18:00"))
    answer(g5, omar, 0, 0, _ts(d5, "11:05"))
    # G5: participants 2, participated 2, completed 1 (finished_at), avg 200/3 = 66.67

    # One-screen class — School B.
    cid = c.execute("INSERT INTO classroom (name, school, teacher_name, program) VALUES (%s, %s, 'T. Two', %s) "
                    "RETURNING id", (f"{TAG} Class 5A", SCHOOL_B, "")).fetchone()[0]
    PK["classroom"].append(cid)
    st = {}
    for n in ("Siti", "Raj", "Mei", "Andy"):
        st[n] = c.execute("INSERT INTO student (classroom_id, name) VALUES (%s, %s) RETURNING id",
                          (cid, n)).fetchone()[0]
        PK["student"].append(st[n])

    def session(name, day, status, present, absent):
        sid = c.execute("INSERT INTO class_session (classroom_id, game_modes, status, started_at) "
                        "VALUES (%s, '{multiple_choice}', %s, %s) RETURNING id",
                        (cid, status, _ts(day, "09:00"))).fetchone()[0]
        PK["session"].append(sid)
        ids[name] = sid
        tid = c.execute("INSERT INTO team (class_session_id, name, emoji, color, position) "
                        "VALUES (%s, 'Tigers', 'x', 'cyan', 1) RETURNING id", (sid,)).fetchone()[0]
        PK["team"].append(tid)
        for n, pres in [(n, True) for n in present] + [(n, False) for n in absent]:
            c.execute("INSERT INTO attendance (class_session_id, student_id, present) VALUES (%s, %s, %s)",
                      (sid, st[n], pres))
            PK["attendance"].append((sid, st[n]))
        return sid, tid

    def turn(sid, tid, no, status, who, best_points, attempts=()):
        c.execute("INSERT INTO class_turn (class_session_id, turn_no, team_id, question_id, status, student_id, "
                  "best_points) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                  (sid, no, tid, q, status, st[who] if who else None, best_points))
        PK["turn"].append((sid, no))
        for k, acc in enumerate(attempts, start=1):
            aid = c.execute("INSERT INTO class_attempt (class_session_id, turn_no, attempt_no, student_id, accuracy, "
                            "passed, stars, points, duration_ms) VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 1000) "
                            "RETURNING id", (sid, no, k, st[who], acc, acc >= 60)).fetchone()[0]
            PK["attempt"].append(aid)

    # S1 2001-03-20 finished: Siti turn (40 then 80 → best 80), Raj turn (100), turn 3 skipped. Andy absent.
    s1, t1 = session("S1", f"{Y}-03-20", "finished", ["Siti", "Raj", "Mei"], ["Andy"])
    turn(s1, t1, 1, "done", "Siti", 50, (40, 80))
    turn(s1, t1, 2, "done", "Raj", 100, (100,))
    turn(s1, t1, 3, "skipped", None, 0)
    # S1: participants 3, participated 2, completed 2 (finished), avg (80+100)/2 = 90
    # S2 2001-04-05 still live with a pending turn → nobody completed.
    s2, t2 = session("S2", f"{Y}-04-05", "live", ["Siti", "Raj"], ["Mei", "Andy"])
    turn(s2, t2, 1, "done", "Siti", 100, (100,))
    turn(s2, t2, 2, "pending", None, 0)
    ids["students"] = st
    ids["players"] = {"aisyah": aisyah, "ben": ben, "dina": dina, "kid": kid, "siti_hw": siti_hw, "omar": omar}
    return ids


def _cleanup():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        for aid in PK["attempt"]:
            c.execute("DELETE FROM class_attempt WHERE id = %s", (aid,))
        for sid, no in PK["turn"]:
            c.execute("DELETE FROM class_turn WHERE class_session_id = %s AND turn_no = %s", (sid, no))
        for sid, stid in PK["attendance"]:
            c.execute("DELETE FROM attendance WHERE class_session_id = %s AND student_id = %s", (sid, stid))
        for tid in PK["team"]:
            c.execute("DELETE FROM team WHERE id = %s", (tid,))
        for sid in PK["session"]:
            c.execute("DELETE FROM class_session WHERE id = %s", (sid,))
        for stid in PK["student"]:
            c.execute("DELETE FROM student WHERE id = %s", (stid,))
        for cid in PK["classroom"]:
            c.execute("DELETE FROM classroom WHERE id = %s", (cid,))
        for aid in PK["answer"]:
            c.execute("DELETE FROM live_answer WHERE id = %s", (aid,))
        for pid in PK["player"]:
            c.execute("DELETE FROM live_player WHERE id = %s", (pid,))
        for gid, idx in PK["lq"]:
            c.execute("DELETE FROM live_question WHERE game_id = %s AND idx = %s", (gid, idx))
        for gid in PK["game"]:
            c.execute("DELETE FROM live_game WHERE id = %s", (gid,))
        for qid in PK["question"]:
            try:
                c.execute("DELETE FROM question WHERE id = %s", (qid,))
            except psycopg.errors.ForeignKeyViolation:
                c.execute("UPDATE question SET is_active = false WHERE id = %s", (qid,))
        for pid in PK["pack"]:
            try:
                c.execute("DELETE FROM question_pack WHERE id = %s", (pid,))
            except psycopg.errors.ForeignKeyViolation:
                c.execute("UPDATE question_pack SET is_active = false WHERE id = %s", (pid,))


@pytest.fixture(scope="module")
def data():
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as c:
            ids = _seed(c)
        yield ids
    finally:
        _cleanup()


@pytest.fixture(scope="module")
def client(data):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh_limiter():
    reports.fail_limiter.clear()
    yield
    reports.fail_limiter.clear()


def get(client, path, **params):
    r = client.get(path, params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def _csv_rows(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith("﻿".encode("utf-8")), "UTF-8 BOM for Excel"
    assert b"\r\n" in r.content
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def _kpi(d, **expected):
    got = {k: d[k] for k in expected}
    assert got == expected


# ------------------------------------------------------------------ access key
def test_key_required_wrong_and_right(client):
    assert client.get("/api/reports/summary").status_code == 401
    r = client.get("/api/reports/summary", headers={"X-Reports-Key": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "Wrong reports access code"
    assert client.get("/api/reports/summary", headers={"X-Reports-Key": ""}).status_code == 401
    for path in ("/api/reports/schools", f"/api/reports/schools/x/sessions",
                 f"/api/reports/sessions/live/{uuid.uuid4()}", "/api/reports/students?school=x"):
        assert client.get(path).status_code == 401, path
    assert client.get("/api/reports/summary", headers=KEY).status_code == 200


def test_key_from_env(client, monkeypatch):
    monkeypatch.setenv("REPORTS_KEY", "s3cret-code")
    assert client.get("/api/reports/summary", headers={"X-Reports-Key": "reports123"}).status_code == 401
    assert client.get("/api/reports/summary", headers={"X-Reports-Key": "s3cret-code"}).status_code == 200
    assert reports.warn_if_not_configured() is False


def test_key_constant_time_path(client, monkeypatch):
    """Every request goes through hmac.compare_digest on two 32-byte sha256 digests — also a missing key."""
    calls = []
    real = reports._compare

    def spy(a, b):
        calls.append((len(a), len(b)))
        return real(a, b)

    monkeypatch.setattr(reports, "_compare", spy)
    client.get("/api/reports/summary")
    client.get("/api/reports/summary", headers={"X-Reports-Key": "x" * 500})
    client.get("/api/reports/summary", headers=KEY)
    assert calls == [(32, 32)] * 3
    assert reports.key_matches(None) is False and reports.key_matches("") is False


def test_failed_attempts_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(reports.fail_limiter, "limit", 3)
    for _ in range(3):
        assert client.get("/api/reports/summary", headers={"X-Reports-Key": "bad"}).status_code == 401
    assert client.get("/api/reports/summary", headers={"X-Reports-Key": "bad"}).status_code == 429
    assert client.get("/api/reports/summary", headers=KEY).status_code == 429  # blocked even with the right code
    reports.fail_limiter.clear()
    assert client.get("/api/reports/summary", headers=KEY).status_code == 200
    # successes are not counted
    for _ in range(5):
        assert client.get("/api/reports/summary", headers=KEY).status_code == 200


def test_unset_key_logs_warning(monkeypatch, caplog):
    monkeypatch.delenv("REPORTS_KEY", raising=False)
    with caplog.at_level(logging.WARNING, logger="playclass"):
        assert reports.warn_if_not_configured() is True
    assert any("REPORTS_KEY is not set" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_unset_key_is_503_not_configured(client, monkeypatch, value):
    """No default credential in code: without REPORTS_KEY every /api/reports/* call is 503, even with the old
    dev code, and failed tries are not counted (nothing to guess)."""
    if value is None:
        monkeypatch.delenv("REPORTS_KEY", raising=False)
    else:
        monkeypatch.setenv("REPORTS_KEY", value)
    for headers in ({}, {"X-Reports-Key": "reports123"}, {"X-Reports-Key": value or "x"}):
        for path in ("/api/reports/summary", "/api/reports/schools", "/api/reports/students?school=x"):
            r = client.get(path, headers=headers)
            assert r.status_code == 503 and r.json()["detail"] == "reports not configured", (path, headers)
    assert reports.key_matches("reports123") is False and reports.key_matches("") is False
    assert client.get("/reports").status_code == 200  # the page itself still loads and shows the message


def test_status_probe(client, monkeypatch):
    """/api/reports/status needs no code (the page probes it on load) and never counts as a failed attempt."""
    reports.fail_limiter.clear()
    assert client.get("/api/reports/status").json() == {"configured": True}
    monkeypatch.delenv("REPORTS_KEY", raising=False)
    r = client.get("/api/reports/status")
    assert r.status_code == 503 and r.json()["detail"] == "reports not configured"
    assert not reports.fail_limiter.blocked("testclient") and not reports.fail_limiter._hits.get("testclient")


def test_reports_page_route(client):
    r = client.get("/reports")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


# ------------------------------------------------------------------ summary
# All fixture sessions are dated in this run's random year Y, so that date range isolates them.
YR = {"from": f"{Y}-01-01", "to": f"{Y}-12-31"}


def test_summary_totals_across_all_schools(client, data):
    d = get(client, "/api/reports/summary", **YR)
    # G1, G2, G4 (School A) + G5, S1, S2 (School B) + G3 (no school)
    _kpi(d, sessions=7, live_games=4, homework_games=1, class_sessions=2, schools=2, sessions_school_not_set=1,
         participants=13, participated=10, participation_rate=0.7692, joined=15, answered_any=11, completed=8,
         completion_rate=0.5333, avg_score_pct=75.29)
    assert d["date_range"] == {"from": f"{Y}-03-01", "to": f"{Y}-05-01"}
    assert d["funnel"] == [{"step": "joined", "count": 15, "pct": 1.0},
                           {"step": "answered", "count": 11, "pct": 0.7333},
                           {"step": "completed", "count": 8, "pct": 0.5333}]
    assert "by_program" not in d and "program" not in d["filters"]  # program is no longer reported


def test_summary_first_two_live_games(client, data):
    d = get(client, "/api/reports/summary", school=TAG, to=f"{Y}-03-15")  # G1 + G2
    _kpi(d, sessions=2, live_games=2, homework_games=0, class_sessions=0, schools=1, participants=6,
         participated=5, participation_rate=0.8333, joined=6, answered_any=5, completed=4, completion_rate=0.6667,
         avg_score_pct=70.0)
    assert d["date_range"] == {"from": f"{Y}-03-01", "to": f"{Y}-03-15"}


def test_summary_school_b_all_kinds(client, data):
    d = get(client, "/api/reports/summary", school=SCHOOL_B)
    # G5 (homework), S1 + S2 (one-screen); unique people: Siti(hw), Omar + Siti, Raj, Mei
    _kpi(d, sessions=3, live_games=0, homework_games=1, class_sessions=2, schools=1, sessions_school_not_set=0,
         participants=5, participated=4, participation_rate=0.8, joined=7, answered_any=5, completed=3,
         completion_rate=0.4286, avg_score_pct=80.0)
    assert d["date_range"] == {"from": f"{Y}-03-20", "to": f"{Y}-04-10"}


def test_summary_mode_filter(client, data):
    hw = get(client, "/api/reports/summary", school=SCHOOL_B, mode="homework")
    _kpi(hw, sessions=1, homework_games=1, participants=2, participated=2, completed=1, completion_rate=0.5,
         avg_score_pct=66.67)
    one = get(client, "/api/reports/summary", school=SCHOOL_B, mode="one-screen")
    _kpi(one, sessions=2, class_sessions=2, participants=3, participated=2, joined=5, answered_any=3, completed=2,
         avg_score_pct=93.33)
    live = get(client, "/api/reports/summary", mode="live", **YR)
    _kpi(live, sessions=4, live_games=4, homework_games=0, class_sessions=0)
    assert client.get("/api/reports/summary", params={"mode": "bogus"}, headers=KEY).status_code == 422


def test_summary_school_filter_and_not_set_school(client, data):
    d = get(client, "/api/reports/summary", school=f"{TAG.upper()} school a")  # ILIKE substring
    _kpi(d, sessions=3, schools=1, participants=7, participated=6, joined=7, completed=5, avg_score_pct=72.73)
    ns = get(client, "/api/reports/summary", school="(not set)", **YR)  # "(not set)" = blank school
    _kpi(ns, sessions=1, schools=0, sessions_school_not_set=1, participants=1, participated=0, avg_score_pct=None)
    # wildcards in the search are literal
    assert get(client, "/api/reports/summary", school=f"{TAG} School %")["sessions"] == 0


def test_program_param_is_deprecated_and_ignored_in_output(client, data):
    # old links may still send ?program= (exact, case-insensitive); nothing is reported per program
    d = get(client, "/api/reports/summary", program=P1.upper(), **YR)
    _kpi(d, sessions=1, participants=4)  # only G1 carries a legacy program value
    s = get(client, f"/api/reports/schools/{TAG} School A/sessions")
    assert all("program" not in i for i in s["items"])
    assert "program" not in get(client, f"/api/reports/sessions/live/{data['G1']}")["session"]


def test_summary_dates_inclusive(client, data):
    d = get(client, "/api/reports/summary", school=TAG, **{"from": f"{Y}-03-10", "to": f"{Y}-03-31"})
    _kpi(d, sessions=2, live_games=1, class_sessions=1, participants=5)  # G2 + S1
    d = get(client, "/api/reports/summary", school=TAG, to=f"{Y}-03-01")  # 'to' includes the whole day
    _kpi(d, sessions=1, participants=4, completed=2, avg_score_pct=66.67)
    d = get(client, "/api/reports/summary", school=TAG, **{"from": f"{Y}-03-02", "to": f"{Y}-03-15"})
    _kpi(d, sessions=1, participants=2)
    r = client.get("/api/reports/summary", params={"from": f"{Y}-05-01", "to": f"{Y}-04-01"}, headers=KEY)
    assert r.status_code == 422


# ------------------------------------------------------------------ schools
def test_schools_numbers_and_not_set_bucket(client, data):
    d = get(client, "/api/reports/schools", **YR)
    assert d["total"] == 3
    by = {i["school"]: i for i in d["items"]}
    assert list(by) == [SCHOOL_A, SCHOOL_B, "(not set)"]  # name order, "(not set)" last
    _kpi(by["(not set)"], sessions=1, live_games=1, participants=1, participated=0, participation_rate=0.0,
         avg_score_pct=None, last_session_date=f"{Y}-04-01")
    _kpi(by[SCHOOL_B], sessions=3, homework_games=1, class_sessions=2, participants=5, participated=4,
         participation_rate=0.8, joined=7, completed=3, completion_rate=0.4286, avg_score_pct=80.0,
         last_session_date=f"{Y}-04-10")
    assert all("program" not in i for i in d["items"])


def test_schools_spelling_merge_sort_and_pagination(client, data):
    d = get(client, "/api/reports/schools", school=TAG)
    assert d["total"] == 2
    a = d["items"][0]
    assert a["school"] == SCHOOL_A  # "School A" x2 wins over "school a " x1
    _kpi(a, sessions=3, participants=7, participated=6, participation_rate=0.8571, completion_rate=0.7143,
         avg_score_pct=72.73, last_session_date=f"{Y}-05-01")
    p1 = get(client, "/api/reports/schools", school=TAG, limit=1)
    p2 = get(client, "/api/reports/schools", school=TAG, limit=1, offset=1)
    assert [len(p1["items"]), len(p2["items"]), p1["total"]] == [1, 1, 2]
    assert [p1["items"][0]["school"], p2["items"][0]["school"]] == [SCHOOL_A, SCHOOL_B]
    s = get(client, "/api/reports/schools", school=TAG, sort="avg_score", dir="desc")
    assert [i["school"] for i in s["items"]] == [SCHOOL_B, SCHOOL_A]
    for bad in ({"limit": 0}, {"limit": 201}, {"offset": -1}, {"sort": "school; drop"}, {"dir": "up"}):
        assert client.get("/api/reports/schools", params=bad, headers=KEY).status_code == 422, bad


def test_schools_csv(client, data):
    r = client.get("/api/reports/schools", params={"school": TAG, "format": "csv", "limit": 1}, headers=KEY)
    rows = _csv_rows(r)
    assert rows[0][:3] == ["school", "sessions", "live_games"]
    assert [x[0] for x in rows[1:]] == [SCHOOL_A, SCHOOL_B]  # CSV exports the whole filtered list
    assert rows[1][rows[0].index("avg_score_pct")] == "72.73"
    fn = r.headers["content-disposition"]
    assert f"reports-schools-{SLUG}-{date.today().isoformat()}.csv" in fn


# ------------------------------------------------------------------ school sessions
def test_school_sessions(client, data):
    d = get(client, f"/api/reports/schools/{TAG} SCHOOL a/sessions")
    assert d["school"] == f"{TAG} SCHOOL a" and d["total"] == 3
    assert [i["id"] for i in d["items"]] == [str(data[g]) for g in ("G4", "G2", "G1")]  # newest first
    g1 = d["items"][2]
    _kpi(g1, kind="live", type="live", title=f"{TAG} G1", date=f"{Y}-03-01", teacher="T. Teacher",
         questions=3, participants=4, participated=3, completed=2, completion_rate=0.5, avg_score_pct=66.67,
         csv_url=None)
    assert g1["report_csv_url"] == f"/api/reports/sessions/live/{data['G1']}?format=csv"
    b = get(client, f"/api/reports/schools/{SCHOOL_B}/sessions")
    assert [(i["type"], i["date"]) for i in b["items"]] == [("homework", f"{Y}-04-10"), ("one-screen", f"{Y}-04-05"),
                                                            ("one-screen", f"{Y}-03-20")]
    s1 = b["items"][2]
    _kpi(s1, participants=3, participated=2, completed=2, avg_score_pct=90.0, title=f"{TAG} Class 5A",
         teacher="T. Two", csv_url=f"/api/class/sessions/{data['S1']}/participation.csv")
    hw = b["items"][0]
    _kpi(hw, kind="homework", participants=2, completed=1, completion_rate=0.5, questions=2, status="ended")
    assert s1["grouping"] == "teams" and hw["grouping"] is None  # one-screen sessions carry grouping (db/013)
    # filters on the path endpoint
    assert get(client, f"/api/reports/schools/{SCHOOL_B}/sessions", mode="homework")["total"] == 1
    assert get(client, f"/api/reports/schools/{SCHOOL_B}/sessions", to=f"{Y}-03-31")["total"] == 1
    assert get(client, f"/api/reports/schools/{SCHOOL_B}/sessions", limit=1, offset=2)["items"][0]["id"] == str(data["S1"])


def test_school_sessions_not_set(client, data):
    d = get(client, "/api/reports/schools/(not set)/sessions", **YR)
    assert d["school"] == "(not set)" and [i["id"] for i in d["items"]] == [str(data["G3"])]
    _kpi(d["items"][0], school="(not set)", questions=0, participants=1, participated=0, avg_score_pct=None,
         completed=0)


def test_school_sessions_csv(client, data):
    r = client.get(f"/api/reports/schools/{SCHOOL_A}/sessions", params={"format": "csv"}, headers=KEY)
    rows = _csv_rows(r)
    assert rows[0][:4] == ["school", "type", "title", "date"] and len(rows) == 4
    assert rows[3][:4] == [SCHOOL_A, "live", f"{TAG} G1", f"{Y}-03-01"]
    assert f"reports-sessions-{SLUG}-school-a-{date.today().isoformat()}.csv" in r.headers["content-disposition"]


# ------------------------------------------------------------------ session detail
def test_session_live_students(client, data):
    d = get(client, f"/api/reports/sessions/live/{data['G1']}")
    assert d["session"]["school"] == SCHOOL_A and d["session"]["questions"] == 3
    rows = [(s["name"], s["present"], s["answered"], s["correct"], s["accuracy_pct"], s["score"], s["rank"],
             s["completed"], s["present_for"]) for s in d["students"]]
    assert rows == [
        ("Aisyah", True, 3, 2, 66.67, 1800, 1, True, 3),
        ("Dina", True, 2, 2, 100.0, 1500, 2, True, 2),     # late join: present for 2 of 3 → completed
        ("Ben", True, 1, 0, 0.0, 0, 3, False, 3),
        ("Chen", True, 0, 0, None, 0, 3, False, 3),        # tie shares rank 3
    ]  # "Kicked Kid" is not listed
    assert d["total"] == 4
    assert [s["name"] for s in get(client, f"/api/reports/sessions/live/{data['G1']}", limit=2, offset=1)["students"]] \
        == ["Dina", "Ben"]


def test_session_class_students(client, data):
    d = get(client, f"/api/reports/sessions/class/{data['S1']}")
    _kpi(d["session"], type="one-screen", participants=3, participated=2, completed=2, avg_score_pct=90.0)
    rows = [(s["name"], s["present"], s["answered"], s["correct"], s["accuracy_pct"], s["score"], s["rank"],
             s["completed"]) for s in d["students"]]
    assert rows == [("Raj", True, 1, 1, 100.0, 100, 1, True), ("Siti", True, 1, 1, 80.0, 50, 2, True),
                    ("Mei", True, 0, 0, None, 0, 3, False), ("Andy", False, 0, 0, None, 0, None, False)]


def test_session_homework_students(client, data):
    d = get(client, f"/api/reports/sessions/homework/{data['G5']}")
    assert d["session"]["status"] == "ended"  # effective status: past closes_at
    rows = [(s["name"], s["answered"], s["completed"], s["progress"], s["total"], bool(s["finished_at"]))
            for s in d["students"]]
    assert rows == [("Siti", 2, True, 2, 2, True), ("Omar", 1, False, 1, 2, False)]
    r = client.get(f"/api/reports/sessions/homework/{data['G5']}", params={"format": "csv"}, headers=KEY)
    csvr = _csv_rows(r)
    assert csvr[0][-2:] == ["progress", "finished_at"] and csvr[1][-2] == "2/2" and csvr[2][-2:] == ["1/2", ""]


def test_session_errors(client, data):
    assert client.get(f"/api/reports/sessions/class/{data['G1']}", headers=KEY).status_code == 404  # wrong kind
    assert client.get(f"/api/reports/sessions/live/{data['G5']}", headers=KEY).status_code == 404   # it's homework
    assert client.get(f"/api/reports/sessions/live/{uuid.uuid4()}", headers=KEY).status_code == 404
    assert client.get(f"/api/reports/sessions/foo/{data['G1']}", headers=KEY).status_code == 422
    assert client.get("/api/reports/sessions/live/not-a-uuid", headers=KEY).status_code == 422
    assert client.get(f"/api/reports/sessions/live/{data['G1']}", params={"limit": 501}, headers=KEY).status_code == 422


def test_session_csv(client, data):
    r = client.get(f"/api/reports/sessions/live/{data['G1']}", params={"format": "csv"}, headers=KEY)
    rows = _csv_rows(r)
    h = rows[0]
    assert h == ["school", "type", "title", "date", "teacher", "name", "present", "answered", "correct",
                 "accuracy_pct", "score", "rank", "completed"]
    assert rows[1][5:] == ["Aisyah", "yes", "3", "2", "66.67", "1800", "1", "yes"]
    assert rows[4][5:] == ["Chen", "yes", "0", "0", "", "0", "3", "no"]
    gid8 = str(data["G1"])[:8]
    assert f"reports-students-{SLUG}-school-a-{Y}-03-01-live-{gid8}.csv" in r.headers["content-disposition"]


# ------------------------------------------------------------------ students progress (name-matched)
def test_students_progress_school_a(client, data):
    d = get(client, "/api/reports/students", school=SCHOOL_A)
    assert d["matching"] == "name, approximate" and "approximate" in d["note"]
    by = {i["match_key"]: i for i in d["items"]}
    assert list(by) == ["aisyah", "ben", "chen", "dina"]
    a = by["aisyah"]  # "Aisyah" (G1), "AISYAH" (G2), "Aisyah" (G4) → one student
    assert [s["score_pct"] for s in a["sessions"]] == [66.67, 100.0, 100.0]
    assert [s["date"] for s in a["sessions"]] == [f"{Y}-03-01", f"{Y}-03-15", f"{Y}-05-01"]
    _kpi(a, sessions_attended=3, sessions_scored=3, first_score_pct=66.67, last_score_pct=100.0, improvement_pct=33.33)
    _kpi(by["ben"], sessions_attended=2, first_score_pct=0.0, last_score_pct=50.0, improvement_pct=50.0)
    _kpi(by["chen"], sessions_attended=1, sessions_scored=0, improvement_pct=None)
    _kpi(by["dina"], sessions_attended=1, sessions_scored=1, improvement_pct=None)  # needs 2 scored sessions
    assert "kicked kid" not in by


def test_students_progress_school_b_filters_and_pages(client, data):
    d = get(client, "/api/reports/students", school=SCHOOL_B.lower())
    by = {i["match_key"]: i for i in d["items"]}
    assert list(by) == ["mei", "omar", "raj", "siti"]  # Andy was never present
    s = by["siti"]  # class S1 80 → class S2 100 → homework 100
    assert [(x["type"], x["score_pct"]) for x in s["sessions"]] == [("one-screen", 80.0), ("one-screen", 100.0),
                                                                    ("homework", 100.0)]
    _kpi(s, improvement_pct=20.0)
    _kpi(by["raj"], sessions_attended=2, sessions_scored=1, improvement_pct=None)
    only_class = get(client, "/api/reports/students", school=SCHOOL_B, mode="one-screen")
    assert [i["match_key"] for i in only_class["items"]] == ["mei", "raj", "siti"]
    early = get(client, "/api/reports/students", school=SCHOOL_B, to=f"{Y}-03-31")
    assert {i["match_key"]: i["sessions_attended"] for i in early["items"]} == {"mei": 1, "raj": 1, "siti": 1}
    pg = get(client, "/api/reports/students", school=SCHOOL_B, limit=2, offset=2)
    assert pg["total"] == 4 and [i["match_key"] for i in pg["items"]] == ["raj", "siti"]
    assert len(pg["items"][1]["sessions"]) == 3  # a page never splits one student's sessions
    assert client.get("/api/reports/students", headers=KEY).status_code == 422  # school is required


def test_students_csv(client, data):
    r = client.get("/api/reports/students", params={"school": SCHOOL_A, "format": "csv"}, headers=KEY)
    rows = _csv_rows(r)
    assert rows[0][1] == "name (matched by name, approximate)"
    a = rows[1]
    assert a[:7] == [SCHOOL_A, "Aisyah", "3", "3", "66.67", "100.00", "33.33"]
    assert a[7] == f"{Y}-03-01 live: 66.67 | {Y}-03-15 live: 100.00 | {Y}-05-01 live: 100.00"
    assert f"reports-progress-{SLUG}-school-a-{date.today().isoformat()}.csv" in r.headers["content-disposition"]


def test_summary_csv(client, data):
    r = client.get("/api/reports/summary", params={"school": SCHOOL_B, "format": "csv"}, headers=KEY)
    rows = _csv_rows(r)
    assert len(rows) == 2 and "program" not in ",".join(rows[0])
    d = dict(zip(rows[0], rows[1]))
    assert d["scope"] == f"schools matching: {SCHOOL_B}" and d["sessions"] == "3" and d["completion_rate"] == "0.4286"
    assert d["avg_score_pct"] == "80.00" and d["date_from"] == f"{Y}-03-20" and d["homework_games"] == "1"
    assert f"reports-summary-{SLUG}-school-b-all-modes-{date.today().isoformat()}.csv" \
        in r.headers["content-disposition"]


def test_reports_are_read_only(client, data):
    """The router runs every query in a READ ONLY transaction."""
    with reports._ro() as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("UPDATE live_game SET title = title WHERE id = %s", (data["G1"],))
