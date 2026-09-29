"""Classroom mode (/api/class) — integration tests against the real dev PostgreSQL. Quiz only: every turn is a
multiple_choice question answered with one tap; speaking turns / audio uploads are rejected with 422.

Fixture data is our own: classrooms named "[pytest] …", packs with slug "pytest-…", questions with
prompt "[pytest-class] …". Every row is tracked by primary key and deleted at the end of the module
(children first); nothing else in the dev DB is touched.
"""
from __future__ import annotations

import io
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:55432/playclass")
TAG = "[pytest]"
QTAG = "[pytest-class]"
RUN = uuid.uuid4().hex[:8]

psycopg = pytest.importorskip("psycopg")


def _db_reachable() -> str | None:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as c:
            c.execute("SELECT 1 FROM class_turn LIMIT 1")
        return None
    except Exception as exc:  # noqa: BLE001
        return f"DATABASE_URL unreachable or db/003_classroom.sql not applied (scripts/dev_db.sh): {exc}"


_reason = _db_reachable()
if _reason:
    pytest.skip(_reason, allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import scoring  # noqa: E402
from app.main import app  # noqa: E402
from tests._seed import insert_pack, insert_question  # noqa: E402

RIGHT, WRONG = 0, 1  # choices for the default question (options ["rice", "bread"], correct_option 0)
SPEAKING_422 = "speaking questions are not supported"

CREATED: dict[str, set] = {"classroom": set(), "pack": set(), "question": set(), "session": set()}


def _cleanup():
    """Delete only rows this module created, by primary key (children first)."""
    cls = list(CREATED["classroom"])
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        sids = {r[0] for r in c.execute("SELECT id FROM class_session WHERE classroom_id = ANY(%s)",
                                        (cls,)).fetchall()} | set(CREATED["session"])
        sids = [str(s) for s in sids]
        c.execute("DELETE FROM class_attempt WHERE class_session_id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM class_turn WHERE class_session_id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM attendance WHERE class_session_id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM team_member WHERE team_id IN "
                  "(SELECT id FROM team WHERE class_session_id = ANY(%s::uuid[]))", (sids,))
        c.execute("DELETE FROM team WHERE class_session_id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM class_session WHERE id = ANY(%s::uuid[])", (sids,))
        c.execute("DELETE FROM student WHERE classroom_id = ANY(%s)", (cls,))
        c.execute("DELETE FROM classroom WHERE id = ANY(%s)", (cls,))
    _delete_or_archive("question", CREATED["question"])
    _delete_or_archive("question_pack", CREATED["pack"])

def _delete_or_archive(table: str, ids) -> None:
    """Delete our rows by PK, one by one. If a row is referenced by rows we did NOT create (another agent or user
    of the shared dev DB played our question), archive it instead of failing — and never roll back the rest."""
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        for i in ids:
            try:
                c.execute(f"DELETE FROM {table} WHERE id = %s", (i,))
            except psycopg.errors.ForeignKeyViolation:
                c.execute(f"UPDATE {table} SET is_active = false WHERE id = %s", (i,))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    _cleanup()


# ------------------------------------------------------------------ builders
def _pack(client, topic="general", **over):
    body = {"slug": f"pytest-{uuid.uuid4().hex[:10]}", "name": f"{TAG} Pack", "topic": topic,
            "description": "d", "why_it_matters": "w", "is_active": True}
    body.update(over)
    # A *private* pack (as a teacher quiz is): "all packs" games of other users of the shared dev DB can then
    # never pick our questions, which used to break this module's teardown (FK).
    p = insert_pack(**body, edit_key_hash=f"pytest-private-{uuid.uuid4().hex}")
    CREATED["pack"].add(p["id"])
    return p


def _question(client, pack_id, **over):
    body = {"prompt": f"{QTAG} What do we eat?", "options": ["rice", "bread"], "correct_option": RIGHT,
            "difficulty": 1, "base_points": 100, "time_limit_sec": 20, "is_active": True, "sort_order": 999}
    body.update(over)
    q = insert_question(pack_id, **body)
    CREATED["question"].add(q["id"])
    return q


def _classroom(client, n_students=4, program=None, name="Kelas 5 Cemerlang"):
    r = client.post("/api/class/classrooms", json={
        "name": f"{TAG} {name} {RUN}", "school": "SK Pytest", "teacher_name": "Cikgu Tes",
        "program": program if program is not None else f"{TAG} Lenovo {RUN}"})
    assert r.status_code == 201, r.text
    c = r.json()
    CREATED["classroom"].add(c["id"])
    names = [f"Murid {i}" for i in range(1, n_students + 1)]
    r = client.post(f"/api/class/classrooms/{c['id']}/students", json={"names": names})
    assert r.status_code == 200, r.text
    c["students"] = r.json()["added"]
    return c


def _session(client, classroom, pack_id, modes=("multiple_choice",), team_count=2, rounds=3, present=None):
    ids = present if present is not None else [s["id"] for s in classroom["students"]]
    r = client.post("/api/class/sessions", json={
        "classroom_id": classroom["id"], "pack_id": pack_id, "game_modes": list(modes),
        "team_count": team_count, "rounds": rounds, "present_student_ids": ids})
    assert r.status_code == 201, r.text
    CREATED["session"].add(r.json()["id"])
    return r.json()


def _attempt(client, sid, turn_no, student_id, choice=WRONG, duration_ms=3000):
    return client.post(f"/api/class/sessions/{sid}/turns/{turn_no}/attempts",
                       data={"student_id": str(student_id), "duration_ms": str(duration_ms), "choice": str(choice)})


def _cur(state):
    return state["turns"][state["current_turn"] - 1]


def _member_of(state, team_id, idx=0):
    team = next(t for t in state["teams"] if t["id"] == team_id)
    return team["members"][idx]["student_id"]


def _other_team_member(state, team_id):
    team = next(t for t in state["teams"] if t["id"] != team_id)
    return team["members"][0]["student_id"]


def _team(state, team_id):
    return next(t for t in state["teams"] if t["id"] == team_id)


def _expected_points(q, accuracy, streak, duration_ms):
    return scoring.compute_points(base_points=q["base_points"], difficulty=q["difficulty"],
                                  accuracy=accuracy, passed=scoring.is_passed(accuracy), streak=streak,
                                  duration_ms=duration_ms, time_limit_sec=q["time_limit_sec"])["points"]


@pytest.fixture(scope="module")
def rice_pack(client):
    """A pack with exactly one multiple_choice question -> every turn is the same (deterministic) question."""
    p = _pack(client, topic="general")
    q = _question(client, p["id"])
    return {**p, "question": q}


# ------------------------------------------------------------------ packs (public list)
def test_public_pack_list_counts_multiple_choice_only(client):
    p = _pack(client, topic="ai", name=f"{TAG} AI Basics")
    _question(client, p["id"], prompt=f"{QTAG} What does AI stand for?", options=["Artificial Intelligence", "Apple"])
    _question(client, p["id"], prompt=f"{QTAG} broken", options=["only one"])          # not playable (1 option)
    _question(client, p["id"], game_mode="read_aloud", prompt=f"{QTAG} legacy speaking", target_text="hello")
    pub = client.get("/api/class/packs").json()
    mine = next(x for x in pub if x["id"] == p["id"])
    assert set(mine) == {"id", "slug", "name", "topic", "description", "why_it_matters", "question_counts"}
    assert mine["question_counts"] == {"multiple_choice": 1} and mine["topic"] == "ai"


def test_admin_api_is_gone(client):
    for method, path in (("get", "/api/admin/packs"), ("post", "/api/admin/packs"), ("put", "/api/admin/packs/1"),
                         ("get", "/api/admin/questions"), ("get", "/admin"), ("get", "/practice")):
        assert client.request(method.upper(), path, json={}).status_code in (404, 405), path


# ------------------------------------------------------------------ classrooms & students
def test_classroom_and_students(client):
    assert client.post("/api/class/classrooms", json={"name": "  "}).status_code == 422
    r = client.post("/api/class/classrooms", json={"name": f"  {TAG} Minimal {RUN} "})
    assert r.status_code == 201
    c = r.json()
    CREATED["classroom"].add(c["id"])
    assert c["name"] == f"{TAG} Minimal {RUN}" and c["school"] == "" and c["program"] == ""
    assert c["student_count"] == 0 and c["last_session_at"] is None

    r = client.post(f"/api/class/classrooms/{c['id']}/students",
                    json={"names": ["  Aisyah ", "", "Ben", "aisyah", "   ", "Chong  Wei", "Ben"]})
    assert r.status_code == 200
    b = r.json()
    assert [s["name"] for s in b["added"]] == ["Aisyah", "Ben", "Chong Wei"] and b["skipped"] == []
    assert all(set(s) == {"id", "name", "is_active"} and s["is_active"] for s in b["added"])
    again = client.post(f"/api/class/classrooms/{c['id']}/students",
                        json={"names": ["ben", "Devi", "AISYAH"]}).json()
    assert [s["name"] for s in again["added"]] == ["Devi"] and again["skipped"] == ["ben", "AISYAH"]
    assert client.post("/api/class/classrooms/999999999/students", json={"names": ["x"]}).status_code == 404

    ids = {s["name"]: s["id"] for s in b["added"] + again["added"]}
    r = client.patch(f"/api/class/students/{ids['Ben']}", json={"name": " Benjamin "})
    assert r.status_code == 200 and r.json()["name"] == "Benjamin" and r.json()["is_active"] is True
    assert client.patch(f"/api/class/students/{ids['Devi']}", json={"is_active": False}).json()["is_active"] is False
    assert client.patch(f"/api/class/students/{ids['Devi']}", json={"name": "Aisyah"}).status_code == 409
    assert client.patch(f"/api/class/students/{ids['Devi']}", json={"name": " "}).status_code == 422
    assert client.patch("/api/class/students/999999999", json={"is_active": True}).status_code == 404

    d = client.get(f"/api/class/classrooms/{c['id']}").json()
    assert d["student_count"] == 3 and len(d["students"]) == 4
    assert {s["name"]: s["is_active"] for s in d["students"]}["Devi"] is False
    lst = client.get("/api/class/classrooms").json()
    row = next(x for x in lst if x["id"] == c["id"])
    assert set(row) >= {"id", "name", "school", "teacher_name", "program", "student_count", "last_session_at"}
    assert row["student_count"] == 3
    assert client.get("/api/class/classrooms/999999999").status_code == 404


# ------------------------------------------------------------------ session creation
def test_create_session_validation(client, rice_pack):
    c = _classroom(client, n_students=3)
    ids = [s["id"] for s in c["students"]]
    ok = {"classroom_id": c["id"], "pack_id": rice_pack["id"], "game_modes": ["multiple_choice"],
          "team_count": 2, "rounds": 3, "present_student_ids": ids}

    def post(**over):
        return client.post("/api/class/sessions", json={**ok, **over})

    assert post(classroom_id=999999999).status_code == 404
    assert post(pack_id=999999999).status_code == 404
    for bad in (dict(team_count=1), dict(team_count=7), dict(rounds=0), dict(rounds=11), dict(game_modes=[]),
                dict(game_modes=["bogus"]), dict(team_count=3, present_student_ids=ids[:2]),
                dict(present_student_ids=[ids[0], ids[0]])):  # duplicates don't count twice
        r = post(**bad)
        assert r.status_code == 422 and isinstance(r.json()["detail"], str), (bad, r.text)
    # student from another classroom / inactive student
    other = _classroom(client, n_students=1, name="Lain")
    assert post(present_student_ids=ids + [other["students"][0]["id"]]).status_code == 422
    client.patch(f"/api/class/students/{ids[2]}", json={"is_active": False})
    r = post()
    assert r.status_code == 422 and "active" in r.json()["detail"]
    client.patch(f"/api/class/students/{ids[2]}", json={"is_active": True})
    # speaking modes are not supported any more
    for modes in (["read_aloud"], ["multiple_choice", "quick_answer"]):
        r = post(game_modes=modes)
        assert r.status_code == 422 and SPEAKING_422 in r.json()["detail"], r.text
    # not enough questions: a pack with only a legacy speaking question has nothing playable
    legacy = _pack(client)
    _question(client, legacy["id"], game_mode="read_aloud", prompt=f"{QTAG} legacy", target_text="hello")
    r = post(pack_id=legacy["id"])
    assert r.status_code == 422 and "question" in r.json()["detail"].lower()
    # archived pack
    arch = _pack(client, is_active=False)
    _question(client, arch["id"])
    assert post(pack_id=arch["id"]).status_code == 422


def test_create_session_state(client):
    p = _pack(client)
    qs = [_question(client, p["id"], prompt=f"{QTAG} Q{i}?", options=[f"yes{i}", f"no{i}"]) for i in range(3)]
    _question(client, p["id"], prompt=f"{QTAG} inactive", is_active=False)
    _question(client, p["id"], game_mode="picture_talk", prompt=f"{QTAG} legacy speaking", keywords=["x"])
    c = _classroom(client, n_students=7)
    present = [s["id"] for s in c["students"][:6]]
    absent = c["students"][6]["id"]
    s = _session(client, c, p["id"], team_count=3, rounds=2, present=present)
    assert set(s) == {"id", "status", "classroom", "pack", "game_modes", "current_turn", "total_turns",
                      "started_at", "finished_at", "teams", "turns", "next", "participation",
                      "grouping", "leaderboard"}
    assert s["grouping"] == "teams" and s["leaderboard"] is None  # teams mode: additive keys only
    assert s["status"] == "live" and s["current_turn"] == 1 and s["total_turns"] == 6
    assert s["classroom"] == {"id": c["id"], "name": c["name"]}
    assert s["pack"] == {"id": p["id"], "name": p["name"], "topic": "general"}
    assert s["game_modes"] == ["multiple_choice"]
    # teams: auto-named, colored, positions 1..n, present students dealt round-robin
    assert [t["position"] for t in s["teams"]] == [1, 2, 3]
    assert [t["color"] for t in s["teams"]] == ["cyan", "pink", "lime"]
    assert [t["emoji"] for t in s["teams"]] == ["🐯", "🦅", "🐬"]
    assert "Tigers" in s["teams"][0]["name"] and "Harimau" in s["teams"][0]["name"]
    assert all(t["score"] == 0 and t["streak"] == 0 and len(t["members"]) == 2 for t in s["teams"])
    dealt = sorted(m["student_id"] for t in s["teams"] for m in t["members"])
    assert dealt == sorted(present) and absent not in dealt
    assert set(s["teams"][0]["members"][0]) == {"student_id", "name", "turns_spoken"}
    # queue: round-robin by team position, pending, public view (no correct_option), no repeats while available
    team_by_pos = [t["id"] for t in s["teams"]]
    assert [t["turn_no"] for t in s["turns"]] == list(range(1, 7))
    assert [t["team_id"] for t in s["turns"]] == team_by_pos * 2
    assert all(t["status"] == "pending" and t["best_points"] == 0 and t["student_id"] is None for t in s["turns"])
    assert set(s["turns"][0]["question"]) == {"id", "game_mode", "prompt", "target_text", "image_url",
                                              "difficulty", "base_points", "time_limit_sec", "options"}
    q0 = s["turns"][0]["question"]
    assert q0["game_mode"] == "multiple_choice" and q0["target_text"] is None and len(q0["options"]) == 2
    order = [t["question"]["id"] for t in s["turns"]]
    assert len(set(order[:3])) == 3 and sorted(order) == sorted([q["id"] for q in qs] * 2)
    # next + participation (absent student counted as not present)
    assert s["next"]["turn_no"] == 1 and s["next"]["team_id"] == team_by_pos[0]
    assert s["next"]["suggested_student_id"] in [m["student_id"] for m in s["teams"][0]["members"]]
    assert s["participation"] == {"present": 6, "spoke": 0, "rate": 0.0}
    assert client.get(f"/api/class/sessions/{s['id']}").json() == s
    assert client.get(f"/api/class/sessions/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/api/class/classrooms/{c['id']}").json()["last_session_at"] is not None


def test_session_without_pack_uses_all_active(client, rice_pack):
    c = _classroom(client, n_students=2)
    s = _session(client, c, None, rounds=1)
    assert s["pack"] is None and s["total_turns"] == 2
    assert all(t["question"]["game_mode"] == "multiple_choice" for t in s["turns"])


# ------------------------------------------------------------------ teams edit
def test_put_teams(client, rice_pack):
    c = _classroom(client, n_students=4)
    s = _session(client, c, rice_pack["id"])
    t1, t2 = s["teams"][0]["id"], s["teams"][1]["id"]
    ids = [x["id"] for x in c["students"]]
    url = f"/api/class/sessions/{s['id']}/teams"
    for bad in ({"teams": [{"team_id": t1, "student_ids": ids}]},                               # missing team
                {"teams": [{"team_id": t1, "student_ids": ids}, {"team_id": t2, "student_ids": []}]},  # empty team
                {"teams": [{"team_id": t1, "student_ids": ids[:2]}, {"team_id": t2, "student_ids": ids[1:]}]},
                {"teams": [{"team_id": t1, "student_ids": ids[:1]}, {"team_id": t2, "student_ids": ids[1:3]}]},
                {"teams": [{"team_id": t1, "student_ids": ids[:2]}, {"team_id": 999999999, "student_ids": ids[2:]}]}):
        assert client.put(url, json=bad).status_code == 422, bad
    r = client.put(url, json={"teams": [{"team_id": t1, "student_ids": ids[:3]},
                                        {"team_id": t2, "student_ids": ids[3:]}]})
    assert r.status_code == 200, r.text
    st = r.json()
    assert sorted(m["student_id"] for m in _team(st, t1)["members"]) == sorted(ids[:3])
    assert [m["student_id"] for m in _team(st, t2)["members"]] == ids[3:]
    assert client.put(f"/api/class/sessions/{uuid.uuid4()}/teams",
                      json={"teams": [{"team_id": t1, "student_ids": ids}, {"team_id": t2, "student_ids": ids}]}
                      ).status_code == 404
    # after an attempt -> 409
    _attempt(client, s["id"], 1, _member_of(st, st["turns"][0]["team_id"]))
    assert client.put(url, json={"teams": [{"team_id": t1, "student_ids": ids[:2]},
                                           {"team_id": t2, "student_ids": ids[2:]}]}).status_code == 409


# ------------------------------------------------------------------ speaker suggestion fairness
def test_suggestion_fairness_and_override(client, rice_pack):
    c = _classroom(client, n_students=4)
    s = _session(client, c, rice_pack["id"], team_count=2, rounds=4)  # 2 members per team, 4 turns each
    suggested: dict[int, list[int]] = {t["id"]: [] for t in s["teams"]}
    st = s
    while st["next"]:
        nxt = st["next"]
        members = [m["student_id"] for m in _team(st, nxt["team_id"])["members"]]
        assert nxt["suggested_student_id"] in members
        fewest = min(m["turns_spoken"] for m in _team(st, nxt["team_id"])["members"])
        assert next(m for m in _team(st, nxt["team_id"])["members"]
                    if m["student_id"] == nxt["suggested_student_id"])["turns_spoken"] == fewest
        suggested[nxt["team_id"]].append(nxt["suggested_student_id"])
        # repeated GETs don't change the suggestion (stable tie-break)
        assert client.get(f"/api/class/sessions/{st['id']}").json()["next"] == nxt
        r = client.post(f"/api/class/sessions/{st['id']}/turns/{nxt['turn_no']}/skip",
                        json={"student_id": nxt["suggested_student_id"]})
        assert r.status_code == 200, r.text
        st = r.json()
    for team_id, picks in suggested.items():
        assert len(picks) == 4 and all(picks.count(sid) == 2 for sid in set(picks)) and len(set(picks)) == 2
    assert all(m["turns_spoken"] == 2 for t in st["teams"] for m in t["members"])
    assert st["current_turn"] == 9 and st["next"] is None and st["status"] == "live"

    # teacher override: any present member of the team may speak, not only the suggested one
    s2 = _session(client, c, rice_pack["id"], rounds=1)
    nxt = s2["next"]
    other = next(m["student_id"] for m in _team(s2, nxt["team_id"])["members"]
                 if m["student_id"] != nxt["suggested_student_id"])
    r = _attempt(client, s2["id"], 1, other)
    assert r.status_code == 200, r.text
    # once someone attempted the turn, the suggestion sticks to them
    assert r.json()["state"]["next"]["suggested_student_id"] == other


# ------------------------------------------------------------------ skip / next / errors
def test_skip_next_and_errors(client, rice_pack):
    c = _classroom(client, n_students=5)
    ids = [x["id"] for x in c["students"]]
    s = _session(client, c, rice_pack["id"], rounds=2, present=ids[:4])
    sid, absent = s["id"], ids[4]
    team1 = s["turns"][0]["team_id"]
    base = f"/api/class/sessions/{sid}/turns"

    # attempt error codes
    assert _attempt(client, str(uuid.uuid4()), 1, ids[0]).status_code == 404
    assert _attempt(client, sid, 99, ids[0]).status_code == 404
    assert _attempt(client, sid, 2, _member_of(s, s["turns"][1]["team_id"])).status_code == 409
    r = _attempt(client, sid, 1, _other_team_member(s, team1))
    assert r.status_code == 422 and "member" in r.json()["detail"]
    assert _attempt(client, sid, 1, absent).status_code == 422
    r = client.post(f"{base}/1/attempts", data={"student_id": str(_member_of(s, team1))},
                    files={"audio": ("a.wav", b"RIFF....WAVE", "audio/wav")})
    assert r.status_code == 422 and r.json()["detail"] == SPEAKING_422
    r = client.post(f"{base}/1/attempts", data={"student_id": str(_member_of(s, team1))})  # no choice
    assert r.status_code == 422 and "choice" in r.json()["detail"]
    r = _attempt(client, sid, 1, _member_of(s, team1), choice=2)                           # out of range
    assert r.status_code == 422 and "choice" in r.json()["detail"]

    # skip: non-member student 422, wrong turn 409, success -> skipped + 0 points + advance
    assert client.post(f"{base}/1/skip", json={"student_id": _other_team_member(s, team1)}).status_code == 422
    assert client.post(f"{base}/2/skip", json={}).status_code == 409
    assert client.post(f"{base}/99/skip", json={}).status_code == 404
    r = client.post(f"{base}/1/skip")  # body optional
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["turns"][0]["status"] == "skipped" and st["turns"][0]["best_points"] == 0
    assert st["turns"][0]["student_id"] is None and st["current_turn"] == 2
    assert client.post(f"{base}/1/skip", json={}).status_code == 409   # double click
    assert client.post(f"{base}/1/next", json={}).status_code == 409

    # next without an attempt -> skipped; with an attempt -> done
    st = client.post(f"{base}/2/next", json={}).json()
    assert st["turns"][1]["status"] == "skipped" and st["current_turn"] == 3
    a = _attempt(client, sid, 3, _member_of(st, st["turns"][2]["team_id"]))
    assert a.status_code == 200, a.text
    assert a.json()["attempt_no"] == 1 and a.json()["turn"]["attempts_left"] == 0
    assert client.post(f"{base}/3/skip", json={}).status_code == 409   # has an attempt: use next
    st = client.post(f"{base}/3/next", json={}).json()
    assert st["turns"][2]["status"] == "done" and st["current_turn"] == 4

    # finished session: everything mutating -> 409, GET still works, finish is idempotent
    f1 = client.post(f"/api/class/sessions/{sid}/finish")
    assert f1.status_code == 200 and f1.json()["state"]["status"] == "finished"
    assert f1.json()["state"]["next"] is None and f1.json()["state"]["finished_at"] is not None
    assert _attempt(client, sid, 4, _member_of(st, st["turns"][3]["team_id"])).status_code == 409
    assert client.post(f"{base}/4/skip", json={}).status_code == 409
    assert client.post(f"{base}/4/next", json={}).status_code == 409
    teams = [{"team_id": t["id"], "student_ids": [m["student_id"] for m in t["members"]]} for t in st["teams"]]
    assert client.put(f"/api/class/sessions/{sid}/teams", json={"teams": teams}).status_code == 409
    f2 = client.post(f"/api/class/sessions/{sid}/finish").json()
    assert f2["state"]["finished_at"] == f1.json()["state"]["finished_at"]
    assert client.post(f"/api/class/sessions/{uuid.uuid4()}/finish").status_code == 404


# ------------------------------------------------------------------ scoring: one tap per turn, streak, skip reset
def test_one_attempt_team_streak_and_skip_reset(client, rice_pack):
    q = rice_pack["question"]
    c = _classroom(client, n_students=4)
    s = _session(client, c, rice_pack["id"], team_count=2, rounds=4)
    sid = s["id"]
    A, B = s["teams"][0]["id"], s["teams"][1]["id"]
    a1_student = _member_of(s, A)

    # turn 1 (A): a fast right answer -> streak 1 + speed bonus; a second tap -> 409
    p = _attempt(client, sid, 1, a1_student, RIGHT, duration_ms=3000).json()
    assert set(p) == {"attempt_no", "transcript", "accuracy", "passed", "stars", "points", "streak",
                      "streak_multiplier", "speed_bonus", "feedback", "turn", "team", "state"}
    assert p["attempt_no"] == 1 and p["passed"] and p["streak"] == 1 and p["streak_multiplier"] == 1.0
    assert p["accuracy"] == 100.0 and p["speed_bonus"] == 10 and p["transcript"] == ""
    assert p["points"] == _expected_points(q, 100.0, 1, 3000)
    assert p["turn"] == {"turn_no": 1, "status": "pending", "best_points": p["points"], "attempts_left": 0}
    assert p["team"] == {"id": A, "score": p["points"], "streak": 1}
    assert p["feedback"]["correct"] is True and p["feedback"]["correct_option"] == RIGHT
    assert p["feedback"]["correct_option_text"] == "rice" and "stt_words" not in p["feedback"]
    r = _attempt(client, sid, 1, a1_student, RIGHT)
    assert r.status_code == 409 and "attempt" in r.json()["detail"]
    st = client.post(f"/api/class/sessions/{sid}/turns/1/next", json={}).json()
    score_a = p["points"]
    assert _team(st, A)["score"] == score_a and st["participation"]["spoke"] == 1

    # turn 2 (B): right but slow -> no speed bonus
    b_student = _member_of(st, B)
    b1 = _attempt(client, sid, 2, b_student, RIGHT, duration_ms=15000).json()
    assert b1["passed"] and b1["speed_bonus"] == 0 and b1["team"] == {"id": B, "score": b1["points"], "streak": 1}
    st = client.post(f"/api/class/sessions/{sid}/turns/2/next", json={}).json()

    # turn 3 (A): second passed turn in a row -> team streak 2, multiplier 1.1
    a3 = _attempt(client, sid, 3, _member_of(st, A, 1), RIGHT, duration_ms=15000).json()
    assert a3["streak"] == 2 and a3["streak_multiplier"] == pytest.approx(1.1)
    assert a3["points"] == _expected_points(q, 100.0, 2, 15000)
    score_a += a3["points"]
    assert a3["team"] == {"id": A, "score": score_a, "streak": 2}
    st = client.post(f"/api/class/sessions/{sid}/turns/3/next", json={}).json()

    # turn 4 (B): skipped -> B streak reset, B score unchanged
    st = client.post(f"/api/class/sessions/{sid}/turns/4/skip", json={}).json()
    assert _team(st, B)["streak"] == 0 and _team(st, B)["score"] == b1["points"]
    # turn 5 (A): a wrong answer resets A's streak, 0 points
    a5 = _attempt(client, sid, 5, a1_student, WRONG, duration_ms=1000).json()
    assert a5["passed"] is False and a5["points"] == 0 and a5["streak"] == 0 and a5["feedback"]["correct"] is False
    assert a5["team"] == {"id": A, "score": score_a, "streak": 0}
    st = client.post(f"/api/class/sessions/{sid}/turns/5/next", json={}).json()
    st = client.post(f"/api/class/sessions/{sid}/turns/6/next", json={}).json()   # B, unattempted -> skipped
    # turn 7 (A): streak restarts at 1
    a7 = _attempt(client, sid, 7, _member_of(st, A), RIGHT, duration_ms=15000).json()
    assert a7["streak"] == 1 and a7["streak_multiplier"] == 1.0
    score_a += a7["points"]
    assert a7["team"]["score"] == score_a == sum(
        t["best_points"] for t in a7["state"]["turns"] if t["team_id"] == A)

    # finish: ranking, MVP, participation
    fin = client.post(f"/api/class/sessions/{sid}/finish").json()
    assert set(fin) == {"state", "ranking", "mvp", "participation"}
    assert fin["ranking"][0] == {"team_id": A, "name": _team(st, A)["name"], "emoji": "🐯",
                                 "score": score_a, "rank": 1}
    assert fin["ranking"][1]["rank"] == 2 and fin["ranking"][1]["score"] == b1["points"]
    per = {x["student_id"]: x for x in fin["participation"]["students"]}
    assert set(next(iter(per.values()))) == {"student_id", "name", "team", "present", "turns", "attempts",
                                             "best_accuracy", "points"}
    assert per[a1_student]["attempts"] == 3 and per[a1_student]["turns"] == 3   # turns 1, 5 + 7
    assert per[a1_student]["points"] == p["points"] + a7["points"]
    assert per[b_student]["attempts"] == 1 and per[b_student]["points"] == b1["points"]
    top = max(per.values(), key=lambda x: x["points"])
    assert fin["mvp"]["student_id"] == top["student_id"] and fin["mvp"]["points"] == top["points"]
    assert fin["mvp"]["team_id"] == A
    spoke = sum(1 for x in per.values() if x["attempts"] > 0)
    assert fin["participation"]["present"] == 4 and fin["participation"]["spoke"] == spoke == 3
    assert fin["participation"]["rate"] == 0.75


def test_legacy_speaking_turn_is_rejected(client, rice_pack):
    """A session whose turn points at a pre-2026-09-28 speaking question: an answer is 422, the teacher skips."""
    c = _classroom(client, n_students=2)
    s = _session(client, c, rice_pack["id"], rounds=1)
    legacy = _question(client, rice_pack["id"], game_mode="read_aloud", prompt=f"{QTAG} legacy", target_text="hi",
                       is_active=False)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("UPDATE class_turn SET question_id = %s WHERE class_session_id = %s AND turn_no = 1",
                     (legacy["id"], s["id"]))
    who = _member_of(s, s["turns"][0]["team_id"])
    r = _attempt(client, s["id"], 1, who, RIGHT)
    assert r.status_code == 422 and r.json()["detail"] == SPEAKING_422
    st = client.post(f"/api/class/sessions/{s['id']}/turns/1/skip", json={})
    assert st.status_code == 200 and st.json()["turns"][0]["status"] == "skipped"


# ------------------------------------------------------------------ concurrency
def test_concurrent_attempts_lock(client, rice_pack):
    """Two taps fired at once on one turn: exactly one is stored (attempt_no 1), the other gets 409; the team
    score is that attempt's points. A double-clicked "next" advances exactly once."""
    q = rice_pack["question"]
    c = _classroom(client, n_students=2)
    s = _session(client, c, rice_pack["id"], rounds=2)
    sid, team1 = s["id"], s["turns"][0]["team_id"]
    who = _member_of(s, team1)
    barrier = threading.Barrier(2)

    def fire(turn_no, choice):
        barrier.wait()
        return _attempt(client, sid, turn_no, who, choice, duration_ms=15000)

    with ThreadPoolExecutor(2) as ex:
        rs = list(ex.map(lambda ch: fire(1, ch), [RIGHT, RIGHT]))
    assert sorted(r.status_code for r in rs) == [200, 409], [r.text for r in rs]
    win = next(r.json() for r in rs if r.status_code == 200)
    assert win["attempt_no"] == 1 and win["streak"] == 1
    assert win["points"] == _expected_points(q, 100.0, 1, 15000)
    st = client.get(f"/api/class/sessions/{sid}").json()
    assert _team(st, team1)["score"] == win["points"] and st["turns"][0]["best_points"] == win["points"]
    assert st["turns"][0]["attempts_used"] == 1
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute("SELECT attempt_no FROM class_attempt WHERE class_session_id = %s AND turn_no = 1 "
                            "ORDER BY attempt_no", (sid,)).fetchall()
    assert [r[0] for r in rows] == [1]

    # double-clicked "next": exactly one advances
    with ThreadPoolExecutor(2) as ex:
        def nxt(_):
            barrier.wait()
            return client.post(f"/api/class/sessions/{sid}/turns/1/next", json={})
        rs = list(ex.map(nxt, range(2)))
    assert sorted(r.status_code for r in rs) == [200, 409]
    assert client.get(f"/api/class/sessions/{sid}").json()["current_turn"] == 2


# ------------------------------------------------------------------ CSV + program reports
def test_csv_and_reports_filter_by_program(client, rice_pack):
    prog = f"{TAG} Apptitude {RUN}"
    other_prog = f"{TAG} Lenovo Malaysia {RUN}"
    c1 = _classroom(client, n_students=3, program=prog, name="Report A")
    c2 = _classroom(client, n_students=2, program=other_prog, name="Report B")
    ids1 = [x["id"] for x in c1["students"]]
    s1 = _session(client, c1, rice_pack["id"], rounds=1, present=ids1[:2])  # 1 absent
    team1 = s1["turns"][0]["team_id"]
    spk = _member_of(s1, team1)
    assert _attempt(client, s1["id"], 1, spk).status_code == 200
    s1b = _session(client, c1, rice_pack["id"], rounds=1, present=ids1)       # same students again
    _session(client, c2, rice_pack["id"], rounds=1)

    r = client.get(f"/api/class/sessions/{s1['id']}/participation.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.lstrip("﻿").strip().split("\r\n")
    assert lines[0] == "school,classroom,program,date,student,team,present,spoke,turns,points,avg_accuracy"
    assert len(lines) == 1 + 3
    import csv as _csv
    rows = list(_csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    by_name = {x["student"]: x for x in rows}
    spk_name = next(x["name"] for x in c1["students"] if x["id"] == spk)
    absent_name = next(x["name"] for x in c1["students"] if x["id"] == ids1[2])
    assert by_name[spk_name]["spoke"] == "yes" and by_name[spk_name]["present"] == "yes"
    assert by_name[spk_name]["turns"] == "1" and by_name[spk_name]["avg_accuracy"] == "0.0"
    assert by_name[absent_name]["present"] == "no" and by_name[absent_name]["team"] == ""
    assert all(x["program"] == prog and x["school"] == "SK Pytest" and x["date"] == date.today().isoformat()
               for x in rows)
    assert client.get(f"/api/class/sessions/{uuid.uuid4()}/participation.csv").status_code == 404

    rep = client.get("/api/class/reports/participation", params={"program": prog}).json()
    assert set(rep) == {"sessions", "classrooms", "unique_students_present", "unique_students_spoke",
                        "by_classroom"}
    assert rep["sessions"] == 2 and rep["classrooms"] == 1
    assert rep["unique_students_present"] == 3 and rep["unique_students_spoke"] == 1
    assert rep["by_classroom"] == [{"classroom_id": c1["id"], "name": c1["name"], "school": "SK Pytest",
                                    "program": prog, "sessions": 2, "present": 3, "spoke": 1}]
    rep2 = client.get("/api/class/reports/participation", params={"program": other_prog.upper()}).json()
    assert [x["classroom_id"] for x in rep2["by_classroom"]] == [c2["id"]] and rep2["unique_students_spoke"] == 0
    today = date.today()
    rng = client.get("/api/class/reports/participation",
                     params={"program": prog, "from": today.isoformat(), "to": today.isoformat()}).json()
    assert rng["sessions"] == 2
    past = client.get("/api/class/reports/participation",
                      params={"program": prog, "to": (today - timedelta(days=1)).isoformat()}).json()
    assert past["sessions"] == 0 and past["by_classroom"] == [] and past["unique_students_present"] == 0
    everything = client.get("/api/class/reports/participation").json()
    assert everything["sessions"] >= 3
    assert client.get("/api/class/reports/participation", params={"from": "not-a-date"}).status_code == 422
    assert s1b["participation"]["present"] == 3


def test_classroom_page(client):
    r = client.get("/classroom")
    if (ROOT / "static" / "classroom.html").is_file():
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    else:
        assert r.status_code == 404


def test_patch_and_archive_classroom(client):
    c = _classroom(client, n_students=1, name="Kelas Arkib")
    cid = c["id"]
    r = client.patch(f"/api/class/classrooms/{cid}", json={"name": f"{TAG} Kelas Arkib 2", "program": " Lenovo "})
    assert r.status_code == 200 and r.json()["name"] == f"{TAG} Kelas Arkib 2" and r.json()["program"] == "Lenovo"
    assert r.json()["is_archived"] is False and len(r.json()["students"]) == 1
    listed = {x["id"]: x for x in client.get("/api/class/classrooms").json()}
    assert cid in listed and listed[cid]["is_archived"] is False
    r = client.patch(f"/api/class/classrooms/{cid}", json={"is_archived": True})
    assert r.status_code == 200 and r.json()["is_archived"] is True and r.json()["name"] == f"{TAG} Kelas Arkib 2"
    assert cid not in [x["id"] for x in client.get("/api/class/classrooms").json()]
    everything = client.get("/api/class/classrooms", params={"include_archived": "true"}).json()
    assert next(x for x in everything if x["id"] == cid)["is_archived"] is True
    assert client.get(f"/api/class/classrooms/{cid}").status_code == 200  # still reachable by id
    r = client.patch(f"/api/class/classrooms/{cid}", json={"is_archived": False})
    assert r.json()["is_archived"] is False and cid in [x["id"] for x in client.get("/api/class/classrooms").json()]
    for bad in ({"name": "  "}, {"name": "x" * 121}, {"is_archived": "maybe"}):
        assert client.patch(f"/api/class/classrooms/{cid}", json=bad).status_code == 422, bad
    assert client.patch("/api/class/classrooms/999999999", json={"name": "x"}).status_code == 404
    assert client.patch(f"/api/class/classrooms/{cid}", json={}).status_code == 200  # no-op
