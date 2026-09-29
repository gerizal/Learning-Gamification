"""Teacher presents — INDIVIDUAL grouping + late arrivals (/api/class, app/classroom.py) — CONTRACT.md
"TEACHER PRESENTS — INDIVIDUAL or GROUPS" and "Presenter individual — implementation notes".

Real dev PostgreSQL. Fixture data is our own and tagged "[pytest-pi]": a private pack (edit_key_hash set, so
nobody else's "all packs" game can pick its questions) with multiple_choice questions, classrooms and students
created through the API. Every row is tracked by primary key and deleted at the end (children first); nothing
else in the dev DB is touched.
"""
from __future__ import annotations

import csv
import io
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:55432/playclass")
REPORTS = {"X-Reports-Key": os.environ["REPORTS_KEY"]}  # set by tests/conftest.py
TAG = "[pytest-pi]"
RUN = uuid.uuid4().hex[:8]
BRAND_COLORS = ["cyan", "pink", "lime", "amber", "violet"]

psycopg = pytest.importorskip("psycopg")


def _db_reachable() -> str | None:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as c:
            c.execute('SELECT "grouping", question_count FROM class_session LIMIT 1')
        return None
    except Exception as exc:  # noqa: BLE001
        return f"DATABASE_URL unreachable or db/013_presenter_individual.sql not applied: {exc.__class__.__name__}"


_reason = _db_reachable()
if _reason:
    pytest.skip(_reason, allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import scoring  # noqa: E402
from app.main import app  # noqa: E402
from tests._seed import insert_pack, insert_question  # noqa: E402

CREATED: dict[str, set] = {"classroom": set(), "pack": set(), "question": set(), "session": set()}


def _dsn() -> str:
    return os.environ["DATABASE_URL"]


def _cleanup():
    """Delete only rows this module created, by primary key (children first)."""
    cls = list(CREATED["classroom"])
    with psycopg.connect(_dsn()) as c:
        sids = [str(s) for s in ({r[0] for r in c.execute(
            "SELECT id FROM class_session WHERE classroom_id = ANY(%s)", (cls,)).fetchall()} | CREATED["session"])]
        team_ids = [r[0] for r in c.execute("SELECT id FROM team WHERE class_session_id = ANY(%s::uuid[])",
                                            (sids,)).fetchall()]
        student_ids = [r[0] for r in c.execute("SELECT id FROM student WHERE classroom_id = ANY(%s)",
                                               (cls,)).fetchall()]
        c.execute("DELETE FROM class_attempt WHERE class_session_id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM class_turn WHERE class_session_id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM attendance WHERE class_session_id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM team_member WHERE team_id = ANY(%s)", (team_ids,))
        c.execute("DELETE FROM team WHERE id = ANY(%s)", (team_ids,))
        c.execute("DELETE FROM class_session WHERE id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM student WHERE id = ANY(%s)", (student_ids,))
        c.execute("DELETE FROM classroom WHERE id = ANY(%s)", (cls,))
    with psycopg.connect(_dsn(), autocommit=True) as c:
        for table, ids in (("question", CREATED["question"]), ("question_pack", CREATED["pack"])):
            for i in ids:
                try:
                    c.execute(f"DELETE FROM {table} WHERE id = %s", (i,))
                except psycopg.errors.ForeignKeyViolation:  # someone else referenced it meanwhile: archive
                    c.execute(f"UPDATE {table} SET is_active = false WHERE id = %s", (i,))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    _cleanup()


# ------------------------------------------------------------------ builders
@pytest.fixture(scope="module")
def mc_pack(client):
    """Private pack with 3 multiple_choice questions (correct option = 0, base 100, difficulty 1)."""
    pack = insert_pack(slug=f"pytest-pi-{uuid.uuid4().hex[:10]}", name=f"{TAG} Pack", topic="general",
                       edit_key_hash=f"pytest-pi-private-{uuid.uuid4().hex}")
    CREATED["pack"].add(pack["id"])
    qs = []
    for i in range(3):
        q = insert_question(pack["id"], prompt=f"{TAG} Q{i}?", options=[f"right{i}", f"wrong{i}", "other"],
                            correct_option=0, sort_order=999)
        CREATED["question"].add(q["id"])
        qs.append(q)
    return {**pack, "questions": qs}


def _classroom(client, n_students=4, name="Kelas"):
    r = client.post("/api/class/classrooms", json={
        "name": f"{TAG} {name} {RUN} {uuid.uuid4().hex[:4]}", "school": f"{TAG} SK {RUN}",
        "teacher_name": "Cikgu PI", "program": f"{TAG} prog {RUN}"})
    assert r.status_code == 201, r.text
    c = r.json()
    CREATED["classroom"].add(c["id"])
    if n_students:
        r = client.post(f"/api/class/classrooms/{c['id']}/students",
                        json={"names": [f"Pelajar {i:02d}" for i in range(1, n_students + 1)]})
        assert r.status_code == 200, r.text
        c["students"] = r.json()["added"]
    else:
        c["students"] = []
    return c


def _post_session(client, classroom, pack_id, present=None, **over):
    ids = present if present is not None else [s["id"] for s in classroom["students"]]
    body = {"classroom_id": classroom["id"], "pack_id": pack_id, "game_modes": ["multiple_choice"],
            "grouping": "individual", "question_count": 5, "present_student_ids": ids}
    body.update(over)
    r = client.post("/api/class/sessions", json=body)
    if r.status_code == 201:
        CREATED["session"].add(r.json()["id"])
    return r


def _session(client, classroom, pack_id, present=None, **over):
    r = _post_session(client, classroom, pack_id, present, **over)
    assert r.status_code == 201, r.text
    return r.json()


def _answer(client, sid, turn_no, student_id, choice=0, duration_ms=0):
    return client.post(f"/api/class/sessions/{sid}/turns/{turn_no}/attempts",
                       data={"student_id": str(student_id), "choice": str(choice), "duration_ms": str(duration_ms)})


def _state(client, sid):
    r = client.get(f"/api/class/sessions/{sid}")
    assert r.status_code == 200, r.text
    return r.json()


def _team_of(state, student_id):
    return next(t for t in state["teams"] if t["members"][0]["student_id"] == student_id)


def _pts(streak, passed=True):
    return scoring.compute_points(base_points=100, difficulty=1, accuracy=100.0 if passed else 0.0, passed=passed,
                                  streak=streak, duration_ms=0, time_limit_sec=20)["points"]


def _db(sql, params=()):
    with psycopg.connect(_dsn()) as c:
        return c.execute(sql, params).fetchall()


def _db_turn(sid, turn_no):
    return _db("SELECT team_id, student_id, status, best_points FROM class_turn "
               "WHERE class_session_id = %s AND turn_no = %s", (sid, turn_no))[0]


def _db_team_member(team_id):
    return [r[0] for r in _db("SELECT student_id FROM team_member WHERE team_id = %s", (team_id,))]


# ------------------------------------------------------------------ create: validation + state shape
def test_create_individual_validation(client, mc_pack):
    c = _classroom(client, n_students=61, name="Big")
    ids = [s["id"] for s in c["students"]]
    base = {"classroom_id": c["id"], "pack_id": mc_pack["id"], "game_modes": ["multiple_choice"],
            "grouping": "individual"}
    for bad in ({"present_student_ids": ids[:5]},                            # question_count omitted
                {"present_student_ids": ids[:5], "question_count": None},
                {"present_student_ids": ids[:5], "question_count": 0},
                {"present_student_ids": ids[:5], "question_count": 51},
                {"present_student_ids": [], "question_count": 5},
                {"present_student_ids": ids, "question_count": 5}):         # 61 > 60
        r = client.post("/api/class/sessions", json={**base, **bad})
        assert r.status_code == 422 and isinstance(r.json()["detail"], str), (bad, r.text)
    r = _post_session(client, c, mc_pack["id"], present=ids[:5], grouping="pairs")
    assert r.status_code == 422
    # unknown / other-classroom student -> 422
    other = _classroom(client, n_students=1, name="Other")
    assert _post_session(client, c, mc_pack["id"], present=ids[:2] + [other["students"][0]["id"]]).status_code == 422
    # boundaries: 1 student, 60 students, 50 questions; team_count / rounds are ignored (even out of range)
    s1 = _session(client, c, mc_pack["id"], present=ids[:1], question_count=1, team_count=1, rounds=99)
    assert s1["total_turns"] == 1 and len(s1["teams"]) == 1
    s60 = _session(client, c, mc_pack["id"], present=ids[:60], question_count=50)
    assert s60["total_turns"] == 50 and len(s60["teams"]) == 60 and s60["participation"]["present"] == 60
    # teams grouping keeps its own rules (team_count required, 2-6, enough students)
    for bad in ({"grouping": "teams"}, {"grouping": "teams", "team_count": 7},
                {"grouping": "teams", "team_count": 3, "present_student_ids": ids[:2]}):
        r = client.post("/api/class/sessions", json={"classroom_id": c["id"], "pack_id": mc_pack["id"],
                                                     "present_student_ids": ids[:4], **bad})
        assert r.status_code == 422, (bad, r.text)
    # DB: grouping + question_count stored
    rows = _db('SELECT "grouping", question_count FROM class_session WHERE id = %s', (s60["id"],))
    assert rows == [("individual", 50)]


def test_individual_state_shape(client, mc_pack):
    c = _classroom(client, n_students=8)
    present = [s["id"] for s in c["students"][:7]]
    absent = c["students"][7]["id"]
    s = _session(client, c, mc_pack["id"], present=present, question_count=6)
    assert s["grouping"] == "individual" and s["status"] == "live" and s["total_turns"] == 6
    assert set(s) == {"id", "status", "grouping", "classroom", "pack", "game_modes", "current_turn", "total_turns",
                      "started_at", "finished_at", "teams", "turns", "next", "participation", "leaderboard"}
    # one team row per present student: name = student name, single member, brand colours cycle
    names = {x["id"]: x["name"] for x in c["students"]}
    assert len(s["teams"]) == 7 and [t["position"] for t in s["teams"]] == list(range(1, 8))
    assert all(len(t["members"]) == 1 and t["name"] == names[t["members"][0]["student_id"]] for t in s["teams"])
    assert [t["color"] for t in s["teams"]] == (BRAND_COLORS * 2)[:7]
    assert sorted(t["members"][0]["student_id"] for t in s["teams"]) == sorted(present)
    assert absent not in [t["members"][0]["student_id"] for t in s["teams"]]
    # untouched pending turns belong to nobody yet
    assert all(t["team_id"] is None and t["student_id"] is None and t["status"] == "pending" for t in s["turns"])
    assert all(t["question"]["options"] and "correct_option" not in t["question"] for t in s["turns"])
    nxt = s["next"]
    assert nxt["turn_no"] == 1 and nxt["suggested_student_id"] in present
    assert nxt["team_id"] == _team_of(s, nxt["suggested_student_id"])["id"]
    assert _state(client, s["id"])["next"] == nxt  # stable suggestion
    lb = s["leaderboard"]
    assert lb["count"] == 7 and len(lb["top"]) == 7
    assert set(lb["top"][0]) == {"rank", "student_id", "team_id", "name", "emoji", "color", "score", "streak",
                                 "turns_spoken"}
    assert all(e["rank"] == 1 and e["score"] == 0 for e in lb["top"])  # everyone tied on 0
    assert [e["name"] for e in lb["top"]] == sorted(e["name"] for e in lb["top"])
    assert s["participation"] == {"present": 7, "spoke": 0, "rate": 0.0}
    # individual sessions have no teams to edit
    r = client.put(f"/api/class/sessions/{s['id']}/teams",
                   json={"teams": [{"team_id": t["id"], "student_ids": [t["members"][0]["student_id"]]}
                                   for t in s["teams"]]})
    assert r.status_code == 409


# ------------------------------------------------------------------ crediting any present student + streak
def test_credit_any_present_student_and_per_student_streak(client, mc_pack):
    c = _classroom(client, n_students=5)
    present = [x["id"] for x in c["students"][:4]]
    absent = c["students"][4]["id"]
    s = _session(client, c, mc_pack["id"], present=present, question_count=6)
    sid = s["id"]
    other_cls = _classroom(client, n_students=1, name="Other")
    # absent / foreign student -> 422; bad choice -> 422 (nothing stored)
    assert _answer(client, sid, 1, absent).status_code == 422
    assert _answer(client, sid, 1, other_cls["students"][0]["id"]).status_code == 422
    assert _answer(client, sid, 1, present[0], choice=7).status_code == 422
    assert _db("SELECT COUNT(*) FROM class_attempt WHERE class_session_id = %s", (sid,)) == [(0,)]

    # the teacher credits a student who is NOT the suggestion -> the turn is re-pointed to their team
    sugg = s["next"]["suggested_student_id"]
    x = next(p for p in present if p != sugg)
    r = _answer(client, sid, 1, x, choice=0)
    assert r.status_code == 200, r.text
    b = r.json()
    tx = _team_of(b["state"], x)["id"]
    assert b["passed"] and b["streak"] == 1 and b["points"] == _pts(1)
    assert b["team"] == {"id": tx, "score": _pts(1), "streak": 1}
    assert b["turn"] == {"turn_no": 1, "status": "pending", "best_points": _pts(1), "attempts_left": 0}
    assert b["feedback"]["correct_option"] == 0
    assert _db_turn(sid, 1) == (tx, x, "pending", _pts(1))
    assert b["state"]["turns"][0]["team_id"] == tx and b["state"]["next"]["suggested_student_id"] == x
    assert b["state"]["next"]["team_id"] == tx
    # second quiz attempt (same or other student) -> 409, DB unchanged
    assert _answer(client, sid, 1, x).status_code == 409
    r = _answer(client, sid, 1, sugg)
    assert r.status_code == 409 and "one attempt" in r.json()["detail"]
    assert _db("SELECT COUNT(*) FROM class_attempt WHERE class_session_id = %s AND turn_no = 1", (sid,)) == [(1,)]
    assert _db_turn(sid, 1)[:2] == (tx, x)

    st = client.post(f"/api/class/sessions/{sid}/turns/1/next", json={}).json()
    # turn 2: someone else, wrong answer -> their streak 0, x keeps 1
    y = next(p for p in present if p != x)
    b2 = _answer(client, sid, 2, y, choice=1).json()
    assert not b2["passed"] and b2["points"] == 0 and b2["streak"] == 0
    client.post(f"/api/class/sessions/{sid}/turns/2/next", json={})
    # turn 3: x again, correct -> per-student streak 2 (x's consecutive correct turns), multiplier 1.1
    b3 = _answer(client, sid, 3, x, choice=0).json()
    assert b3["streak"] == 2 and b3["streak_multiplier"] == pytest.approx(1.1) and b3["points"] == _pts(2)
    assert b3["team"] == {"id": tx, "score": _pts(1) + _pts(2), "streak": 2}
    client.post(f"/api/class/sessions/{sid}/turns/3/next", json={})
    # turn 4: x wrong -> streak reset; turn 5: x skipped by name -> still 0; turn 6: x correct -> streak 1
    assert _answer(client, sid, 4, x, choice=2).json()["streak"] == 0
    client.post(f"/api/class/sessions/{sid}/turns/4/next", json={})
    r = client.post(f"/api/class/sessions/{sid}/turns/5/skip", json={"student_id": absent})
    assert r.status_code == 422
    st = client.post(f"/api/class/sessions/{sid}/turns/5/skip", json={"student_id": x}).json()
    assert st["turns"][4]["student_id"] == x and st["turns"][4]["team_id"] == tx
    assert st["turns"][4]["status"] == "skipped"
    b6 = _answer(client, sid, 6, x).json()
    assert b6["streak"] == 1 and b6["team"]["score"] == _pts(1) + _pts(2) + _pts(1)
    # DB: every resolved turn of x points at x's team; y's team has only its own turn
    ty = _team_of(b6["state"], y)["id"]
    rows = _db("SELECT turn_no, team_id, student_id FROM class_turn WHERE class_session_id = %s ORDER BY turn_no",
               (sid,))
    assert [(n, t) for n, t, st_ in rows if st_ == x] == [(1, tx), (3, tx), (4, tx), (5, tx), (6, tx)]
    assert [(n, t, st_) for n, t, st_ in rows if n == 2] == [(2, ty, y)]
    assert _db("SELECT score, streak FROM team WHERE id = %s", (ty,)) == [(0, 0)]
    # all other (never credited) teams have score 0 and are the placeholder owners of nothing resolved
    scores = dict(_db("SELECT id, score FROM team WHERE class_session_id = %s", (sid,)))
    assert scores[tx] == _pts(1) + _pts(2) + _pts(1) and sum(scores.values()) == scores[tx]


def test_next_without_attempt_is_charged_to_the_suggested_student(client, mc_pack):
    c = _classroom(client, n_students=3)
    s = _session(client, c, mc_pack["id"], question_count=3)
    sid = s["id"]
    sugg = s["next"]["suggested_student_id"]
    st = client.post(f"/api/class/sessions/{sid}/turns/1/next", json={}).json()
    assert st["turns"][0]["status"] == "skipped" and st["turns"][0]["student_id"] == sugg
    assert st["turns"][0]["team_id"] == _team_of(st, sugg)["id"]
    assert _team_of(st, sugg)["members"][0]["turns_spoken"] == 1
    assert st["next"]["suggested_student_id"] != sugg  # rotation moved on
    # skip without a name: charged to the suggestion as well
    sugg2 = st["next"]["suggested_student_id"]
    st = client.post(f"/api/class/sessions/{sid}/turns/2/skip", json={}).json()
    assert st["turns"][1]["student_id"] == sugg2 and st["next"]["suggested_student_id"] not in (sugg, sugg2)
    assert _db_turn(sid, 2)[:3] == (_team_of(st, sugg2)["id"], sugg2, "skipped")
    assert st["participation"]["spoke"] == 0  # nobody answered


# ------------------------------------------------------------------ fairness over 30 students x 30 questions
def test_fairness_30_students_30_questions(client, mc_pack):
    c = _classroom(client, n_students=30, name="Thirty")
    s = _session(client, c, mc_pack["id"], question_count=30)
    sid, st = s["id"], s
    picked = []
    while st["next"]:
        nxt = st["next"]
        everyone = [t["members"][0] for t in st["teams"]]
        fewest = min(m["turns_spoken"] for m in everyone)
        chosen = next(m for m in everyone if m["student_id"] == nxt["suggested_student_id"])
        assert chosen["turns_spoken"] == fewest, (nxt, fewest)
        assert _state(client, sid)["next"] == nxt  # stable tie-break across GETs
        picked.append(nxt["suggested_student_id"])
        n = nxt["turn_no"]
        if n % 7 == 0:  # a few unanswered turns: charged to the suggested student anyway
            r = client.post(f"/api/class/sessions/{sid}/turns/{n}/next", json={})
        else:
            assert _answer(client, sid, n, nxt["suggested_student_id"], choice=n % 2).status_code == 200
            r = client.post(f"/api/class/sessions/{sid}/turns/{n}/next", json={})
        assert r.status_code == 200, r.text
        st = r.json()
    assert len(picked) == 30 and sorted(picked) == sorted(x["id"] for x in c["students"])  # everyone exactly once
    assert all(t["members"][0]["turns_spoken"] == 1 for t in st["teams"])
    assert st["current_turn"] == 31 and st["next"] is None
    # DB: each of the 30 turns is credited to a distinct student and points at that student's team
    rows = _db("""SELECT ct.student_id, tm.student_id FROM class_turn ct JOIN team_member tm ON tm.team_id = ct.team_id
                   WHERE ct.class_session_id = %s""", (sid,))
    assert len(rows) == 30 and all(a == b for a, b in rows) and len({a for a, _ in rows}) == 30


# ------------------------------------------------------------------ leaderboard ordering
def test_leaderboard_ordering_top10_and_count(client, mc_pack):
    c = _classroom(client, n_students=12, name="Board")
    s = _session(client, c, mc_pack["id"], question_count=8)
    sid = s["id"]
    ids = sorted(x["id"] for x in c["students"])
    # A answers 3 correct in a row (streak bonus), B 2 correct, C and D 1 correct each (tie), E wrong once
    a, b, cc, d, e = ids[5], ids[2], ids[9], ids[0], ids[11]
    plan = [(a, 0), (b, 0), (a, 0), (cc, 0), (a, 0), (d, 0), (b, 0), (e, 1)]
    for n, (who, choice) in enumerate(plan, start=1):
        assert _answer(client, sid, n, who, choice=choice).status_code == 200
        st = client.post(f"/api/class/sessions/{sid}/turns/{n}/next", json={}).json()
    lb = st["leaderboard"]
    assert lb["count"] == 12 and len(lb["top"]) == 10
    names = {x["id"]: x["name"] for x in c["students"]}
    score = {i: 0 for i in ids}
    score[a] = _pts(1) + _pts(2) + _pts(3)
    score[b] = _pts(1) + _pts(2)  # b's two correct turns are consecutive for b (per-student streak) -> 1, 2
    score[cc] = score[d] = _pts(1)
    expected = sorted(ids, key=lambda i: (-score[i], names[i].lower(), i))
    assert [x["student_id"] for x in lb["top"]] == expected[:10]
    assert [x["score"] for x in lb["top"]] == [score[i] for i in expected[:10]]
    ranks = [x["rank"] for x in lb["top"]]
    assert ranks[:4] == [1, 2, 3, 3] and all(r == 5 for r in ranks[4:])  # ties share a rank
    top_a = lb["top"][0]
    assert top_a["streak"] == 3 and top_a["turns_spoken"] == 3 and top_a["name"] == names[a]
    # the leaderboard is derived from the team rows (DB) — they agree
    db_scores = dict(_db("""SELECT tm.student_id, t.score FROM team t JOIN team_member tm ON tm.team_id = t.id
                             WHERE t.class_session_id = %s""", (sid,)))
    assert db_scores == score


# ------------------------------------------------------------------ finale, participation, CSV, reports
def test_finale_participation_csv_and_reports(client, mc_pack):
    c = _classroom(client, n_students=5, name="Finale")
    present = [x["id"] for x in c["students"][:4]]
    absent = c["students"][4]["id"]
    names = {x["id"]: x["name"] for x in c["students"]}
    s = _session(client, c, mc_pack["id"], present=present, question_count=4)
    sid = s["id"]
    p1, p2, p3, p4 = present
    _answer(client, sid, 1, p1, 0); client.post(f"/api/class/sessions/{sid}/turns/1/next", json={})
    _answer(client, sid, 2, p2, 0); client.post(f"/api/class/sessions/{sid}/turns/2/next", json={})
    _answer(client, sid, 3, p1, 0); client.post(f"/api/class/sessions/{sid}/turns/3/next", json={})
    _answer(client, sid, 4, p3, 1)  # wrong; p4 never answers
    r = client.post(f"/api/class/sessions/{sid}/finish")
    assert r.status_code == 200, r.text
    fin = r.json()
    assert set(fin) == {"state", "ranking", "mvp", "participation"}
    assert fin["state"]["status"] == "finished" and fin["state"]["next"] is None
    # finale ranking: per student, every present student, ties share a rank
    rk = fin["ranking"]
    assert set(rk[0]) == {"student_id", "team_id", "name", "emoji", "color", "score", "rank"}
    assert [x["student_id"] for x in rk][:2] == [p1, p2] and len(rk) == 4
    assert rk[0]["score"] == _pts(1) + _pts(2) and rk[1]["score"] == _pts(1)
    assert [x["rank"] for x in rk] == [1, 2, 3, 3]
    assert sorted(x["student_id"] for x in rk[2:]) == sorted([p3, p4])
    assert fin["mvp"] == {"student_id": p1, "name": names[p1], "team_id": rk[0]["team_id"], "points": rk[0]["score"]}
    # participation = present / answered at least once
    part = fin["participation"]
    assert (part["present"], part["spoke"], part["rate"]) == (4, 3, 0.75)
    by = {x["student_id"]: x for x in part["students"]}
    assert set(by) == set(present) | {absent}
    assert by[p1]["turns"] == 2 and by[p1]["attempts"] == 2 and by[p1]["points"] == rk[0]["score"]
    assert by[p4]["attempts"] == 0 and by[p4]["present"] is True and by[p4]["best_accuracy"] is None
    assert by[absent]["present"] is False and all(x["team"] is None for x in part["students"])
    # finish is idempotent; late arrivals / attempts after finish -> 409
    again = client.post(f"/api/class/sessions/{sid}/finish").json()
    assert again["state"]["finished_at"] == fin["state"]["finished_at"] and again["ranking"] == rk
    assert client.post(f"/api/class/sessions/{sid}/students", json={"names": ["Late"]}).status_code == 409
    assert _answer(client, sid, 4, p4).status_code == 409

    # CSV: one row per attendance row (per student), team column empty in individual mode
    r = client.get(f"/api/class/sessions/{sid}/participation.csv")
    assert r.status_code == 200 and r.text.startswith("﻿")
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    assert len(rows) == 5
    row = {x["student"]: x for x in rows}
    assert row[names[p1]]["spoke"] == "yes" and row[names[p1]]["points"] == str(rk[0]["score"])
    assert row[names[p1]]["turns"] == "2" and row[names[p1]]["avg_accuracy"] == "100.0"
    assert row[names[p4]]["spoke"] == "no" and row[names[p4]]["present"] == "yes"
    assert row[names[absent]]["present"] == "no" and all(x["team"] == "" for x in rows)
    assert [x["student"] for x in rows][:4] == sorted(names[i] for i in present)  # present first, by name

    # reports compatibility: classroom-program report + /api/reports session detail and school list
    rep = client.get("/api/class/reports/participation", params={"program": f"{TAG} prog {RUN}"}).json()
    mine = next(x for x in rep["by_classroom"] if x["classroom_id"] == c["id"])
    assert (mine["sessions"], mine["present"], mine["spoke"]) == (1, 4, 3)
    r = client.get(f"/api/reports/sessions/class/{sid}", headers=REPORTS)
    assert r.status_code == 200, r.text
    det = r.json()
    assert det["session"]["type"] == "one-screen" and det["session"]["questions"] == 4
    studs = {x["id"]: x for x in det["students"]}
    assert set(studs) == set(present) | {absent}
    assert studs[p1]["answered"] == 2 and studs[p1]["correct"] == 2 and studs[p1]["score"] == rk[0]["score"]
    assert studs[p1]["rank"] == 1 and studs[p3]["answered"] == 1 and studs[p3]["correct"] == 0
    assert studs[p4]["answered"] == 0 and studs[absent]["present"] is False
    r = client.get(f"/api/reports/sessions/class/{sid}", headers=REPORTS, params={"format": "csv"})
    assert r.status_code == 200 and names[p1] in r.text
    r = client.get(f"/api/reports/schools/{TAG} SK {RUN}/sessions", headers=REPORTS)
    assert r.status_code == 200, r.text
    assert any(i["id"] == sid for i in r.json()["items"])


# ------------------------------------------------------------------ late arrivals
def test_late_arrivals_individual(client, mc_pack):
    c = _classroom(client, n_students=4, name="Late")
    present = [x["id"] for x in c["students"][:3]]
    absent = c["students"][3]
    s = _session(client, c, mc_pack["id"], present=present, question_count=6)
    sid = s["id"]
    # everyone present takes a turn first
    st = s
    for n in (1, 2, 3):
        _answer(client, sid, n, st["next"]["suggested_student_id"])
        st = client.post(f"/api/class/sessions/{sid}/turns/{n}/next", json={}).json()
    existing_present = c["students"][0]["name"]
    r = client.post(f"/api/class/sessions/{sid}/students", json={"names": [
        f"  {TAG}   Newbie  ", f"{TAG} newbie", existing_present.upper(), absent["name"].lower(), "   ",
        "x" * 101]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {"added", "skipped", "state"}
    assert [a["name"] for a in out["added"]] == [f"{TAG} Newbie", absent["name"]]
    assert [a["new_student"] for a in out["added"]] == [True, False]
    assert out["added"][1]["student_id"] == absent["id"]
    assert out["skipped"] == [existing_present.upper(), "x" * 101]
    st = out["state"]
    assert len(st["teams"]) == 5 and [t["position"] for t in st["teams"]] == [1, 2, 3, 4, 5]
    new_ids = [a["student_id"] for a in out["added"]]
    for a in out["added"]:
        t = _team_of(st, a["student_id"])
        assert t["id"] == a["team_id"] and t["name"] == a["name"] and t["color"] in BRAND_COLORS
        assert _db_team_member(a["team_id"]) == [a["student_id"]]
    assert st["participation"]["present"] == 5 and st["leaderboard"]["count"] == 5
    # newcomers have 0 turns -> the next suggestion is one of them
    assert st["next"]["suggested_student_id"] in new_ids
    # DB: attendance present for both (absent one flipped), one roster row created, no duplicate name
    att = dict(_db("SELECT student_id, present FROM attendance WHERE class_session_id = %s", (sid,)))
    assert all(att[i] for i in new_ids) and len(att) == 5
    assert _db("SELECT COUNT(*) FROM student WHERE classroom_id = %s AND lower(name) = lower(%s)",
               (c["id"], f"{TAG} Newbie")) == [(1,)]
    # adding the same names again -> skipped (already present), nothing changes
    r = client.post(f"/api/class/sessions/{sid}/students", json={"names": [f"{TAG} NEWBIE"]}).json()
    assert r["added"] == [] and r["skipped"] == [f"{TAG} NEWBIE"] and len(r["state"]["teams"]) == 5
    # the newcomer can be credited right away
    assert _answer(client, sid, 4, new_ids[0]).status_code == 200
    assert client.post(f"/api/class/sessions/{uuid.uuid4()}/students", json={"names": ["x"]}).status_code == 404
    assert client.post(f"/api/class/sessions/{sid}/students", json={"names": []}).status_code == 422


def test_late_arrivals_individual_cap_60(client, mc_pack):
    c = _classroom(client, n_students=61, name="Cap")
    s = _session(client, c, mc_pack["id"], present=[x["id"] for x in c["students"][:60]], question_count=1)
    r = client.post(f"/api/class/sessions/{s['id']}/students", json={"names": [c["students"][60]["name"]]})
    assert r.status_code == 422
    assert _db("SELECT COUNT(*) FROM team WHERE class_session_id = %s", (s["id"],)) == [(60,)]


def test_late_arrivals_teams_go_to_smallest_team(client, mc_pack):
    c = _classroom(client, n_students=5, name="LateTeams")
    s = _session(client, c, mc_pack["id"], grouping="teams", team_count=2, rounds=1, question_count=None)
    assert s["grouping"] == "teams" and s["leaderboard"] is None
    sizes = {t["id"]: len(t["members"]) for t in s["teams"]}
    small = min(sizes, key=lambda k: (sizes[k], [t["position"] for t in s["teams"] if t["id"] == k][0]))
    assert sorted(sizes.values()) == [2, 3]
    r = client.post(f"/api/class/sessions/{s['id']}/students", json={"names": [f"{TAG} Late A"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["added"][0]["team_id"] == small and out["added"][0]["new_student"] is True
    assert sorted(len(t["members"]) for t in out["state"]["teams"]) == [3, 3]
    # next two: first to the lower position (tie), then the other
    out = client.post(f"/api/class/sessions/{s['id']}/students",
                      json={"names": [f"{TAG} Late B", f"{TAG} Late C"]}).json()
    pos1 = out["state"]["teams"][0]["id"]
    pos2 = out["state"]["teams"][1]["id"]
    assert [a["team_id"] for a in out["added"]] == [pos1, pos2]
    assert sorted(len(t["members"]) for t in out["state"]["teams"]) == [4, 4]
    assert len(out["state"]["teams"]) == 2 and out["state"]["participation"]["present"] == 8
    # the newcomer is a present member of their team: may answer that team's turn
    t1 = out["state"]["turns"][0]["team_id"]
    newcomer = next(a["student_id"] for a in out["added"] if a["team_id"] == t1)
    assert _answer(client, s["id"], 1, newcomer).status_code == 200


# ------------------------------------------------------------------ concurrency (DB state asserted)
def test_concurrent_attempts_same_turn_different_students(client, mc_pack):
    """Two attempts at once on the same turn crediting DIFFERENT students: exactly one wins; the turn points at the
    winner's team, the loser's team got nothing, exactly one class_attempt row. Repeated over several turns."""
    c = _classroom(client, n_students=6, name="RaceA")
    s = _session(client, c, mc_pack["id"], question_count=5)
    sid = s["id"]
    ids = [x["id"] for x in c["students"]]
    team_of = {t["members"][0]["student_id"]: t["id"] for t in s["teams"]}
    for n in range(1, 6):
        pair = [ids[(2 * n) % 6], ids[(2 * n + 1) % 6]]
        barrier = threading.Barrier(2)

        def fire(who):
            barrier.wait()
            return who, _answer(client, sid, n, who, choice=0)

        with ThreadPoolExecutor(2) as ex:
            res = list(ex.map(fire, pair))
        codes = sorted(r.status_code for _, r in res)
        assert codes == [200, 409], [r.text for _, r in res]
        winner = next(w for w, r in res if r.status_code == 200)
        loser = next(w for w, r in res if r.status_code == 409)
        rows = _db("SELECT student_id, attempt_no FROM class_attempt WHERE class_session_id = %s AND turn_no = %s",
                   (sid, n))
        assert rows == [(winner, 1)]
        assert _db_turn(sid, n) == (team_of[winner], winner, "pending", _pts(_streak_before(sid, winner, n) + 1))
        assert _db("SELECT COUNT(*) FROM class_turn WHERE class_session_id = %s AND team_id = %s AND turn_no = %s",
                   (sid, team_of[loser], n)) == [(0,)]
        assert client.post(f"/api/class/sessions/{sid}/turns/{n}/next", json={}).status_code == 200
    # team scores = SUM(best_points) of the turns pointing at them (never double counted)
    for tid, score in _db("SELECT id, score FROM team WHERE class_session_id = %s", (sid,)):
        assert score == _db("SELECT COALESCE(SUM(best_points), 0) FROM class_turn WHERE class_session_id = %s "
                            "AND team_id = %s", (sid, tid))[0][0]
    assert _db("SELECT COUNT(*) FROM class_attempt WHERE class_session_id = %s", (sid,)) == [(5,)]


def _streak_before(sid, student_id, turn_no):
    """Consecutive correct resolved turns of the student before turn_no (all answers here are correct)."""
    rows = _db("SELECT turn_no, student_id FROM class_turn WHERE class_session_id = %s AND turn_no < %s "
               "ORDER BY turn_no", (sid, turn_no))
    return sum(1 for _, s in rows if s == student_id)


def test_late_add_racing_an_attempt(client, mc_pack):
    """A late-arrival add and an attempt fired at once (both lock the session row): both succeed, in some order;
    the newcomer has exactly one team row + membership + attendance, the attempt is stored once and the turn points
    at the answering student's team. Individual and teams groupings, several rounds."""
    for grouping in ("individual", "teams"):
        c = _classroom(client, n_students=4, name=f"RaceB-{grouping}")
        extra = {"grouping": "teams", "team_count": 2, "rounds": 3} if grouping == "teams" else {"question_count": 6}
        s = _session(client, c, mc_pack["id"], **extra)
        sid = s["id"]
        for n in range(1, 4):
            st = _state(client, sid)
            who = st["next"]["suggested_student_id"]
            barrier = threading.Barrier(2)
            newname = f"{TAG} Racer {grouping} {n}"

            def do_add():
                barrier.wait()
                return client.post(f"/api/class/sessions/{sid}/students", json={"names": [newname]})

            def do_attempt():
                barrier.wait()
                return _answer(client, sid, n, who, choice=0)

            with ThreadPoolExecutor(2) as ex:
                fa, fb = ex.submit(do_add), ex.submit(do_attempt)
                ra, rb = fa.result(), fb.result()
            assert ra.status_code == 200 and rb.status_code == 200, (ra.text, rb.text)
            new_id = ra.json()["added"][0]["student_id"]
            att = _db("SELECT present FROM attendance WHERE class_session_id = %s AND student_id = %s", (sid, new_id))
            assert att == [(True,)]
            mem = _db("""SELECT tm.team_id FROM team_member tm JOIN team t ON t.id = tm.team_id
                          WHERE t.class_session_id = %s AND tm.student_id = %s""", (sid, new_id))
            assert len(mem) == 1
            assert _db("SELECT student_id FROM class_attempt WHERE class_session_id = %s AND turn_no = %s",
                       (sid, n)) == [(who,)]
            turn_team, turn_student = _db_turn(sid, n)[:2]
            assert turn_student == who
            assert who in _db_team_member(turn_team)
            if grouping == "individual":
                assert _db_team_member(mem[0][0]) == [new_id]
                positions = [r[0] for r in _db("SELECT position FROM team WHERE class_session_id = %s "
                                               "ORDER BY position", (sid,))]
                assert positions == list(range(1, 5 + n))  # unique, gap-free
            else:
                sizes = sorted(r[0] for r in _db(
                    """SELECT COUNT(*) FROM team_member tm JOIN team t ON t.id = tm.team_id
                        WHERE t.class_session_id = %s GROUP BY t.id""", (sid,)))
                assert sizes[-1] - sizes[0] <= 1  # smallest-team rule keeps teams balanced
            assert client.post(f"/api/class/sessions/{sid}/turns/{n}/next", json={}).status_code == 200


def test_double_next_advances_once(client, mc_pack):
    c = _classroom(client, n_students=3, name="RaceC")
    s = _session(client, c, mc_pack["id"], question_count=4)
    sid = s["id"]
    for n, answered in ((1, True), (2, False)):
        st = _state(client, sid)
        sugg = st["next"]["suggested_student_id"]
        if answered:
            assert _answer(client, sid, n, sugg).status_code == 200
        barrier = threading.Barrier(2)

        def nxt(_):
            barrier.wait()
            return client.post(f"/api/class/sessions/{sid}/turns/{n}/next", json={})

        with ThreadPoolExecutor(2) as ex:
            rs = list(ex.map(nxt, range(2)))
        assert sorted(r.status_code for r in rs) == [200, 409]
        assert _db("SELECT current_turn FROM class_session WHERE id = %s", (sid,)) == [(n + 1,)]
        team_id, student_id, status, pts = _db_turn(sid, n)
        assert student_id == sugg and status == ("done" if answered else "skipped")
        assert _db_team_member(team_id) == [sugg]
        assert _db("SELECT COUNT(*) FROM class_attempt WHERE class_session_id = %s AND turn_no = %s",
                   (sid, n)) == [(1 if answered else 0,)]
    # the charged student has exactly the turns counted once each
    st = _state(client, sid)
    assert sum(t["members"][0]["turns_spoken"] for t in st["teams"]) == 2


# ------------------------------------------------------------------ quiz only: a turn is one tap by one student
def test_individual_turn_one_tap_and_no_audio(client, mc_pack):
    cl = _classroom(client, n_students=2, name="OneTap")
    s = _session(client, cl, mc_pack["id"], question_count=1)
    a, b = (x["id"] for x in cl["students"])
    url = f"/api/class/sessions/{s['id']}/turns/1/attempts"
    r = client.post(url, data={"student_id": str(a)}, files={"audio": ("a.wav", b"RIFF....WAVE", "audio/wav")})
    assert r.status_code == 422 and r.json()["detail"] == "speaking questions are not supported"
    assert client.post(url, data={"student_id": str(a), "choice": "0"}).status_code == 200
    r = client.post(url, data={"student_id": str(b), "choice": "0"})
    assert r.status_code == 409 and r.json()["detail"] == "one attempt for quiz"
    assert _db("SELECT student_id FROM class_attempt WHERE class_session_id = %s ORDER BY attempt_no",
               (s["id"],)) == [(a,)]
