"""Classroom mode ("Mode Kelas") — routes under /api/class. Quiz only: multiple_choice turns (one tap per turn);
speaking turns / audio uploads are rejected with 422 "speaking questions are not supported".

See CONTRACT.md "CLASSROOM MODE". Scoring reuses app/scoring.py; only the streak source differs
(team streak = consecutive passed turns of that team instead of the session streak).

grouping = 'individual' ("Teacher presents — individual", db/013) reuses the same tables: one team row per
present student, so the team streak / score machinery becomes a per-student streak / score. A turn's team_id is
re-pointed to the credited student's team under the same session + turn locks.

Concurrency: every mutation of a live session first takes `SELECT ... FOR UPDATE` on the
class_session row (and the class_turn row it touches), so attempts / next / skip / team edits on
one session serialise. The DB-heavy parts run in the threadpool, so the locks really contend.
"""
from __future__ import annotations

import csv
import io
import random
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator, model_validator

from . import db, scoring

router = APIRouter(prefix="/api/class", tags=["classroom"])

MC = scoring.MULTIPLE_CHOICE
MC_MAX_ATTEMPTS = 1  # quiz turn: one tap, no second try (the answer would be obvious)
SPEAKING_UNSUPPORTED = "speaking questions are not supported"  # 422 detail (owner, 2026-09-28: quiz-only MVP)
# Only multiple_choice is playable, and only with 2-4 options and a valid correct_option.
PLAYABLE_SQL = ("(game_mode = 'multiple_choice' AND cardinality(options) BETWEEN 2 AND 4 "
                "AND correct_option IS NOT NULL AND correct_option < cardinality(options))")

# Fixed fun list: (emoji, BM name, EN name, color token). Team i (1-based position) gets entry i-1.
TEAM_NAMES = [
    ("🐯", "Harimau", "Tigers", "cyan"),
    ("🦅", "Helang", "Eagles", "pink"),
    ("🐬", "Lumba-lumba", "Dolphins", "lime"),
    ("🦊", "Rubah", "Foxes", "amber"),
    ("🐘", "Gajah", "Elephants", "violet"),
    ("🦜", "Kakak Tua", "Parrots", "orange"),
]

PACK_COLS = "id, slug, name, topic, description, why_it_matters, is_active, created_at"

# Teacher presents — individual grouping (db/013): one team row per present student.
TEAMS, INDIVIDUAL = "teams", "individual"
BRAND = TEAM_NAMES[:5]           # individual: mascots / colours cycle through the 5 brand colours
MAX_INDIVIDUAL_STUDENTS = 60     # present students per individual session (incl. late arrivals)
LEADERBOARD_TOP = 10


# --------------------------------------------------------------------------- helpers

def _num(v: Any) -> Any:
    return float(v) if isinstance(v, Decimal) else v


def _row(r: dict | None) -> dict | None:
    return None if r is None else {k: _num(v) for k, v in r.items()}


def _rate(spoke: int, present: int) -> float:
    return round(spoke / present, 4) if present else 0.0


def _strip_nonblank(v: Optional[str], field: str) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        raise ValueError(f"{field} must not be blank")
    return v


def _question_counts(conn, pack_ids: list[int]) -> dict[int, dict[str, int]]:
    """Playable questions per pack, keyed by type (multiple_choice is the only type since 2026-09-28)."""
    out = {pid: {MC: 0} for pid in pack_ids}
    if not pack_ids:
        return out
    for r in conn.execute(
        f"""SELECT pack_id, COUNT(*)::int AS n FROM question
             WHERE is_active AND pack_id = ANY(%s) AND {PLAYABLE_SQL} GROUP BY pack_id""",
        (pack_ids,),
    ).fetchall():
        out[r["pack_id"]][MC] = r["n"]
    return out


def _get_session_row(conn, sid: UUID, lock: bool = False) -> dict:
    row = conn.execute(
        "SELECT * FROM class_session WHERE id = %s" + (" FOR UPDATE" if lock else ""), (sid,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Class session not found")
    return row


def _total_turns(conn, sid: UUID) -> int:
    return conn.execute("SELECT COUNT(*)::int AS n FROM class_turn WHERE class_session_id = %s",
                        (sid,)).fetchone()["n"]


def _lock_current_turn(conn, sid: UUID, turn_no: int) -> tuple[dict, dict]:
    """Lock session + turn for a live-session mutation. 404 unknown, 409 finished / not current."""
    sess = _get_session_row(conn, sid, lock=True)
    turn = conn.execute(
        "SELECT * FROM class_turn WHERE class_session_id = %s AND turn_no = %s FOR UPDATE",
        (sid, turn_no),
    ).fetchone()
    if not turn:
        raise HTTPException(404, f"Turn {turn_no} not found")
    if sess["status"] != "live":
        raise HTTPException(409, "Session already finished")
    if sess["current_turn"] != turn_no:
        raise HTTPException(409, f"Turn {turn_no} is not the current turn ({sess['current_turn']})")
    return sess, turn


def _is_present_member(conn, sid: UUID, team_id: int, student_id: int) -> bool:
    return conn.execute(
        """SELECT 1 FROM team_member tm
             JOIN attendance a ON a.student_id = tm.student_id AND a.class_session_id = %s AND a.present
            WHERE tm.team_id = %s AND tm.student_id = %s""",
        (sid, team_id, student_id),
    ).fetchone() is not None


def _team_turn_history(conn, team_id: int, before_turn: Optional[int] = None) -> list[dict]:
    return conn.execute(
        """SELECT t.turn_no, t.status, t.best_points,
                  EXISTS (SELECT 1 FROM class_attempt a WHERE a.class_session_id = t.class_session_id
                            AND a.turn_no = t.turn_no AND a.passed) AS passed,
                  EXISTS (SELECT 1 FROM class_attempt a WHERE a.class_session_id = t.class_session_id
                            AND a.turn_no = t.turn_no) AS attempted
             FROM class_turn t
            WHERE t.team_id = %s AND (%s::int IS NULL OR t.turn_no < %s::int)
            ORDER BY t.turn_no""",
        (team_id, before_turn, before_turn),
    ).fetchall()


def _streak_from(history: list[dict]) -> int:
    """Consecutive passed turns of the team; a skip or a failed (resolved/attempted) turn resets it."""
    streak = 0
    for t in history:
        if t["status"] == "skipped":
            streak = 0
        elif t["status"] == "done" or t["attempted"]:
            streak = streak + 1 if t["passed"] else 0
        # pending + unattempted: not played yet -> ignored
    return streak


def _recompute_team(conn, team_id: int) -> dict:
    """team.score = SUM(best_points) and team.streak recomputed from history — never incremented."""
    hist = _team_turn_history(conn, team_id)
    score = sum(t["best_points"] for t in hist)
    streak = _streak_from(hist)
    return conn.execute("UPDATE team SET score = %s, streak = %s WHERE id = %s RETURNING id, score, streak",
                        (score, streak, team_id)).fetchone()


def _turns_spoken(conn, sid: UUID) -> dict[int, int]:
    """Distinct turns a student attempted in, or was assigned on skip."""
    rows = conn.execute(
        """SELECT student_id, COUNT(DISTINCT turn_no)::int AS n FROM (
               SELECT turn_no, student_id FROM class_turn
                WHERE class_session_id = %(s)s AND student_id IS NOT NULL
               UNION
               SELECT turn_no, student_id FROM class_attempt WHERE class_session_id = %(s)s
           ) x GROUP BY student_id""",
        {"s": sid},
    ).fetchall()
    return {r["student_id"]: r["n"] for r in rows}


def _participation_counts(conn, sid: UUID) -> dict:
    r = conn.execute(
        """SELECT (SELECT COUNT(*) FROM attendance WHERE class_session_id = %(s)s AND present)::int AS present,
                  (SELECT COUNT(DISTINCT student_id) FROM class_attempt WHERE class_session_id = %(s)s)::int AS spoke""",
        {"s": sid},
    ).fetchone()
    return {"present": r["present"], "spoke": r["spoke"], "rate": _rate(r["spoke"], r["present"])}


def _insert_individual_team(conn, sid: UUID, position: int, student_name: str) -> int:
    emoji, _bm, _en, color = BRAND[(position - 1) % len(BRAND)]
    return conn.execute(
        """INSERT INTO team (class_session_id, name, emoji, color, position)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (sid, student_name, emoji, color, position),
    ).fetchone()["id"]


def _individual_team_id(conn, sid: UUID, student_id: int) -> Optional[int]:
    """The team row of a PRESENT student in an individual session (None if not present / no row)."""
    r = conn.execute(
        """SELECT tm.team_id FROM team_member tm
             JOIN team t ON t.id = tm.team_id AND t.class_session_id = %(s)s
             JOIN attendance a ON a.student_id = tm.student_id AND a.class_session_id = %(s)s AND a.present
            WHERE tm.student_id = %(st)s""",
        {"s": sid, "st": student_id},
    ).fetchone()
    return r["team_id"] if r else None


def _teams_and_members(conn, sid: UUID) -> tuple[list[dict], dict[int, list[dict]]]:
    spoken = _turns_spoken(conn, sid)
    teams = conn.execute(
        "SELECT id, name, emoji, color, position, score, streak FROM team "
        "WHERE class_session_id = %s ORDER BY position",
        (sid,),
    ).fetchall()
    members = conn.execute(
        """SELECT tm.team_id, s.id AS student_id, s.name
             FROM team_member tm JOIN team t ON t.id = tm.team_id JOIN student s ON s.id = tm.student_id
            WHERE t.class_session_id = %s ORDER BY s.name, s.id""",
        (sid,),
    ).fetchall()
    by_team: dict[int, list[dict]] = {t["id"]: [] for t in teams}
    for m in members:
        by_team[m["team_id"]].append({"student_id": m["student_id"], "name": m["name"],
                                      "turns_spoken": spoken.get(m["student_id"], 0)})
    return teams, by_team


def _individual_suggestion(conn, sid: UUID, turn: dict) -> tuple[Optional[int], Optional[int]]:
    """(student_id, team_id) the server suggests for an individual-mode turn (same rule as the state)."""
    teams, by_team = _teams_and_members(conn, sid)
    everyone = [m for t in teams for m in by_team[t["id"]]]
    stud = _suggest(sid, turn["turn_no"], turn, everyone)
    return stud, _team_of(teams, by_team, stud)


def _team_of(teams: list[dict], by_team: dict[int, list[dict]], student_id: Optional[int]) -> Optional[int]:
    for t in teams:
        if any(m["student_id"] == student_id for m in by_team[t["id"]]):
            return t["id"]
    return None


def _leaderboard_entries(teams: list[dict], by_team: dict[int, list[dict]]) -> list[dict]:
    """Individual mode: one entry per student, ordered score desc, name, id; competition rank (1, 1, 3)."""
    rows = []
    for t in teams:
        for m in by_team[t["id"]]:
            rows.append({"student_id": m["student_id"], "team_id": t["id"], "name": m["name"],
                         "emoji": t["emoji"], "color": t["color"], "score": t["score"], "streak": t["streak"],
                         "turns_spoken": m["turns_spoken"]})
    rows.sort(key=lambda r: (-r["score"], r["name"].lower(), r["student_id"]))
    prev, rank = None, 0
    for i, r in enumerate(rows, start=1):
        if r["score"] != prev:
            rank, prev = i, r["score"]
        r["rank"] = rank
    return rows


def _state(conn, sid: UUID) -> dict:
    """SessionState per CONTRACT.md."""
    sess = conn.execute(
        """SELECT cs.id, cs.status, cs.game_modes, cs.current_turn, cs.started_at, cs.finished_at,
                  cs."grouping",
                  c.id AS classroom_id, c.name AS classroom_name,
                  p.id AS pack_id, p.name AS pack_name, p.topic AS pack_topic
             FROM class_session cs
             JOIN classroom c ON c.id = cs.classroom_id
        LEFT JOIN question_pack p ON p.id = cs.pack_id
            WHERE cs.id = %s""",
        (sid,),
    ).fetchone()
    if not sess:
        raise HTTPException(404, "Class session not found")
    individual = sess["grouping"] == INDIVIDUAL

    teams, by_team = _teams_and_members(conn, sid)

    turns = conn.execute(
        """SELECT t.turn_no, t.team_id, t.status, t.student_id, t.best_points,
                  (SELECT COUNT(*) FROM class_attempt a WHERE a.class_session_id = t.class_session_id
                      AND a.turn_no = t.turn_no)::int AS attempts_used,
                  q.id AS q_id, q.game_mode, q.prompt, q.target_text, q.image_url, q.difficulty, q.options,
                  q.base_points, q.time_limit_sec
             FROM class_turn t JOIN question q ON q.id = t.question_id
            WHERE t.class_session_id = %s ORDER BY t.turn_no""",
        (sid,),
    ).fetchall()
    turn_out = [{
        # individual: a turn belongs to nobody until it is attempted / resolved (the stored team_id of an
        # untouched pending turn is only a placeholder) -> null.
        "turn_no": t["turn_no"],
        "team_id": (None if individual and t["status"] == "pending" and not t["attempts_used"] else t["team_id"]),
        "status": t["status"],
        "student_id": t["student_id"], "best_points": t["best_points"], "attempts_used": t["attempts_used"],
        "question": {"id": t["q_id"], "game_mode": t["game_mode"], "prompt": t["prompt"],
                     "target_text": None, "image_url": t["image_url"],  # target_text: speaking-only, kept for shape
                     "difficulty": t["difficulty"], "base_points": t["base_points"],
                     "time_limit_sec": t["time_limit_sec"],
                     # multiple_choice: options only — correct_option is never in the state.
                     "options": list(t["options"]) if t["game_mode"] == MC else None},
    } for t in turns]

    nxt = None
    cur = sess["current_turn"]
    if sess["status"] == "live" and 1 <= cur <= len(turns):
        t = turns[cur - 1]
        if individual:
            # any present student may answer; suggestion = fewest turns among everyone present
            everyone = [m for tm in teams for m in by_team[tm["id"]]]
            stud = _suggest(sid, cur, t, everyone)
            nxt = {"turn_no": cur, "team_id": _team_of(teams, by_team, stud), "suggested_student_id": stud}
        else:
            nxt = {"turn_no": cur, "team_id": t["team_id"],
                   "suggested_student_id": _suggest(sid, cur, t, by_team.get(t["team_id"], []))}

    leaderboard = None
    if individual:
        entries = _leaderboard_entries(teams, by_team)
        leaderboard = {"top": entries[:LEADERBOARD_TOP], "count": len(entries)}

    return {
        "id": str(sess["id"]),
        "status": sess["status"],
        "grouping": sess["grouping"],
        "classroom": {"id": sess["classroom_id"], "name": sess["classroom_name"]},
        "pack": ({"id": sess["pack_id"], "name": sess["pack_name"], "topic": sess["pack_topic"]}
                 if sess["pack_id"] is not None else None),
        "game_modes": list(sess["game_modes"]),
        "current_turn": cur,
        "total_turns": len(turns),
        "started_at": sess["started_at"],
        "finished_at": sess["finished_at"],
        "teams": [{**t, "members": by_team[t["id"]]} for t in teams],
        "turns": turn_out,
        "next": nxt,
        "participation": _participation_counts(conn, sid),
        "leaderboard": leaderboard,
    }


def _suggest(sid: UUID, turn_no: int, turn: dict, members: list[dict]) -> Optional[int]:
    """Member with the fewest turns so far; ties broken randomly but stable for this turn
    (seeded by session + turn, so repeated GETs don't flicker). If someone already attempted
    this turn, keep suggesting them."""
    if turn["student_id"] is not None:
        return turn["student_id"]
    if not members:
        return None
    fewest = min(m["turns_spoken"] for m in members)
    cands = sorted(m["student_id"] for m in members if m["turns_spoken"] == fewest)
    return random.Random(f"{sid}:{turn_no}").choice(cands)


def _state_now(sid: UUID) -> dict:
    with db.connection() as conn:
        return _state(conn, sid)


# --------------------------------------------------------------------------- models

class ClassroomIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    school: Optional[str] = Field(default="", max_length=200)
    teacher_name: Optional[str] = Field(default="", max_length=120)
    program: Optional[str] = Field(default="", max_length=120)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _strip_nonblank(v, "name")

    @field_validator("school", "teacher_name", "program")
    @classmethod
    def _opt(cls, v: Optional[str]) -> str:
        return (v or "").strip()


class StudentsIn(BaseModel):
    names: list[str] = Field(max_length=500)


class StudentPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        return _strip_nonblank(v, "name")


class ClassSessionIn(BaseModel):
    classroom_id: int
    pack_id: Optional[int] = None
    game_modes: list[str] = Field(default_factory=lambda: [MC], min_length=1)
    grouping: Literal["teams", "individual"] = TEAMS
    # Range checks are per grouping (below): individual ignores team_count / rounds, teams ignore question_count.
    team_count: Optional[int] = None
    rounds: int = 3
    question_count: Optional[int] = None
    present_student_ids: list[int]

    @field_validator("game_modes", "present_student_ids")
    @classmethod
    def _dedupe(cls, v: list) -> list:
        return list(dict.fromkeys(v))

    @field_validator("game_modes")
    @classmethod
    def _mc_only(cls, v: list) -> list:
        if any(m != MC for m in v):
            raise ValueError(f"{SPEAKING_UNSUPPORTED} (only {MC!r})")
        return v

    @model_validator(mode="after")
    def _enough(self) -> "ClassSessionIn":
        n = len(self.present_student_ids)
        if self.grouping == INDIVIDUAL:
            if self.question_count is None:
                raise ValueError("question_count: required for grouping 'individual' (1-50)")
            if not 1 <= self.question_count <= 50:
                raise ValueError("question_count: must be between 1 and 50")
            if not 1 <= n <= MAX_INDIVIDUAL_STUDENTS:
                raise ValueError(f"present_student_ids: need 1-{MAX_INDIVIDUAL_STUDENTS} present students "
                                 f"(got {n})")
            return self
        if self.team_count is None:
            raise ValueError("team_count: Field required")
        if not 2 <= self.team_count <= 6:
            raise ValueError("team_count: must be between 2 and 6")
        if not 1 <= self.rounds <= 10:
            raise ValueError("rounds: must be between 1 and 10")
        if n < self.team_count:
            raise ValueError(f"need at least {self.team_count} present students for {self.team_count} teams "
                             f"(got {n})")
        return self


class LateStudentsIn(BaseModel):
    names: list[str] = Field(min_length=1, max_length=100)


class TeamAssign(BaseModel):
    team_id: int
    student_ids: list[int] = Field(min_length=1)


class TeamsIn(BaseModel):
    teams: list[TeamAssign] = Field(min_length=2)


class SkipIn(BaseModel):
    student_id: Optional[int] = None


# --------------------------------------------------------------------------- packs

@router.get("/packs")
def list_packs():
    with db.connection() as conn:
        packs = conn.execute(
            f"SELECT {PACK_COLS} FROM question_pack WHERE is_active ORDER BY topic, name, id").fetchall()
        counts = _question_counts(conn, [p["id"] for p in packs])
    return [{k: p[k] for k in ("id", "slug", "name", "topic", "description", "why_it_matters")}
            | {"question_counts": counts[p["id"]]} for p in packs]


# --------------------------------------------------------------------------- classrooms & students

CLASSROOM_COLS = "id, name, school, teacher_name, program, created_at"


@router.get("/classrooms")
def list_classrooms(include_archived: bool = False):
    """Archived classrooms (PATCH is_archived) are hidden unless ?include_archived=true."""
    with db.connection() as conn:
        return conn.execute(
            """SELECT c.id, c.name, c.school, c.teacher_name, c.program, c.created_at, c.is_archived,
                      (SELECT COUNT(*) FROM student s WHERE s.classroom_id = c.id AND s.is_active)::int
                          AS student_count,
                      (SELECT MAX(started_at) FROM class_session cs WHERE cs.classroom_id = c.id)
                          AS last_session_at
                 FROM classroom c
                WHERE %s OR NOT c.is_archived
                ORDER BY c.name, c.id""", (include_archived,)
        ).fetchall()


class ClassroomPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    program: Optional[str] = Field(default=None, max_length=120)
    is_archived: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        return _strip_nonblank(v, "name")

    @field_validator("program")
    @classmethod
    def _prog(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else v.strip()


@router.patch("/classrooms/{classroom_id}")
def patch_classroom(classroom_id: int, body: ClassroomPatch):
    """Rename / re-label / archive a classroom (archived = hidden from the saved-class list; data kept)."""
    with db.connection() as conn:
        if not conn.execute("SELECT 1 FROM classroom WHERE id = %s FOR UPDATE", (classroom_id,)).fetchone():
            raise HTTPException(404, "Classroom not found")
        try:
            with conn.transaction():
                conn.execute(
                    """UPDATE classroom SET name = COALESCE(%s, name), program = COALESCE(%s, program),
                              is_archived = COALESCE(%s, is_archived) WHERE id = %s""",
                    (body.name, body.program, body.is_archived, classroom_id))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "A classroom with this name already exists")
        out = _classroom_detail(conn, classroom_id)
        out["is_archived"] = conn.execute("SELECT is_archived FROM classroom WHERE id = %s",
                                          (classroom_id,)).fetchone()["is_archived"]
        return out


@router.post("/classrooms", status_code=201)
def create_classroom(body: ClassroomIn):
    with db.connection() as conn:
        row = conn.execute(
            f"""INSERT INTO classroom (name, school, teacher_name, program) VALUES (%s, %s, %s, %s)
                RETURNING {CLASSROOM_COLS}""",
            (body.name, body.school, body.teacher_name, body.program),
        ).fetchone()
    return {**row, "student_count": 0, "last_session_at": None}


def _classroom_detail(conn, classroom_id: int) -> dict:
    c = conn.execute(f"SELECT {CLASSROOM_COLS} FROM classroom WHERE id = %s", (classroom_id,)).fetchone()
    if not c:
        raise HTTPException(404, "Classroom not found")
    students = conn.execute(
        "SELECT id, name, is_active FROM student WHERE classroom_id = %s ORDER BY lower(name), id",
        (classroom_id,),
    ).fetchall()
    last = conn.execute("SELECT MAX(started_at) AS t FROM class_session WHERE classroom_id = %s",
                        (classroom_id,)).fetchone()["t"]
    return {**c, "student_count": sum(1 for s in students if s["is_active"]), "last_session_at": last,
            "students": students}


@router.get("/classrooms/{classroom_id}")
def get_classroom(classroom_id: int):
    with db.connection() as conn:
        return _classroom_detail(conn, classroom_id)


@router.post("/classrooms/{classroom_id}/students")
def add_students(classroom_id: int, body: StudentsIn):
    with db.connection() as conn:
        # Lock the classroom so two concurrent pastes can't race on the unique (classroom_id, name).
        if not conn.execute("SELECT 1 FROM classroom WHERE id = %s FOR UPDATE", (classroom_id,)).fetchone():
            raise HTTPException(404, "Classroom not found")
        existing = {r["name"].lower() for r in conn.execute(
            "SELECT name FROM student WHERE classroom_id = %s", (classroom_id,)).fetchall()}
        seen: set[str] = set()
        added, skipped = [], []
        for raw in body.names:
            name = " ".join(str(raw).split())  # trim + collapse inner whitespace
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue  # duplicate inside the paste: deduped silently
            seen.add(key)
            if key in existing or len(name) > 100:
                skipped.append(name)
                continue
            added.append(conn.execute(
                "INSERT INTO student (classroom_id, name) VALUES (%s, %s) RETURNING id, name, is_active",
                (classroom_id, name),
            ).fetchone())
    return {"added": added, "skipped": skipped}


@router.patch("/students/{student_id}")
def patch_student(student_id: int, body: StudentPatch):
    try:
        with db.connection() as conn:
            row = conn.execute(
                """UPDATE student SET name = COALESCE(%s, name), is_active = COALESCE(%s, is_active)
                    WHERE id = %s RETURNING id, classroom_id, name, is_active""",
                (body.name, body.is_active, student_id),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, f"Another student in this classroom is already named {body.name!r}")
    if not row:
        raise HTTPException(404, "Student not found")
    return row


# --------------------------------------------------------------------------- sessions

@router.post("/sessions", status_code=201)
def create_session(body: ClassSessionIn):
    # One connection block = one transaction: session, teams, members, attendance and turn queue
    # are all written or none are.
    with db.connection() as conn:
        if not conn.execute("SELECT 1 FROM classroom WHERE id = %s", (body.classroom_id,)).fetchone():
            raise HTTPException(404, "Classroom not found")
        if body.pack_id is not None:
            pack = conn.execute("SELECT id, is_active FROM question_pack WHERE id = %s",
                                (body.pack_id,)).fetchone()
            if not pack:
                raise HTTPException(404, "Pack not found")
            if not pack["is_active"]:
                raise HTTPException(422, "Pack is archived")

        active = {r["id"] for r in conn.execute(
            "SELECT id FROM student WHERE classroom_id = %s AND is_active", (body.classroom_id,)).fetchall()}
        bad = [i for i in body.present_student_ids if i not in active]
        if bad:
            raise HTTPException(422, f"Not active students of this classroom: {bad}")

        qids = [r["id"] for r in conn.execute(
            f"""SELECT id FROM question
                 WHERE is_active AND (%s::bigint IS NULL OR pack_id = %s::bigint)
                   AND {PLAYABLE_SQL}
                   AND (%s::bigint IS NOT NULL OR pack_id IS NULL OR NOT EXISTS (SELECT 1 FROM question_pack qp
                        WHERE qp.id = question.pack_id AND qp.edit_key_hash IS NOT NULL))""",
            (body.pack_id, body.pack_id, body.pack_id),
        ).fetchall()]
        if not qids:
            raise HTTPException(422, "Not enough questions: no active multiple_choice questions for this pack")

        rng = random.SystemRandom()
        individual = body.grouping == INDIVIDUAL
        total = body.question_count if individual else body.rounds * body.team_count
        queue: list[int] = []
        while len(queue) < total:  # no repeats until the pool is used up, then reshuffle
            batch = qids[:]
            rng.shuffle(batch)
            if queue and len(batch) > 1 and batch[0] == queue[-1]:
                batch[0], batch[-1] = batch[-1], batch[0]
            queue.extend(batch)
        queue = queue[:total]

        sid = conn.execute(
            """INSERT INTO class_session (classroom_id, pack_id, game_modes, "grouping", question_count)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (body.classroom_id, body.pack_id, list(body.game_modes), body.grouping,
             body.question_count if individual else None),
        ).fetchone()["id"]

        present = body.present_student_ids[:]
        rng.shuffle(present)
        team_ids = []
        if individual:
            # one team row per present student (name = student name), positions = shuffled order
            names = {r["id"]: r["name"] for r in conn.execute(
                "SELECT id, name FROM student WHERE id = ANY(%s)", (present,)).fetchall()}
            for pos, stud in enumerate(present, start=1):
                team_ids.append(_insert_individual_team(conn, sid, pos, names[stud]))
            members = list(zip(team_ids, present))
        else:
            for pos in range(1, body.team_count + 1):
                emoji, bm, en, color = TEAM_NAMES[pos - 1]
                team_ids.append(conn.execute(
                    """INSERT INTO team (class_session_id, name, emoji, color, position)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (sid, f"{bm} / {en}", emoji, color, pos),
                ).fetchone()["id"])
            members = [(team_ids[i % len(team_ids)], s) for i, s in enumerate(present)]

        with conn.cursor() as cur:
            cur.executemany("INSERT INTO team_member (team_id, student_id) VALUES (%s, %s)", members)
            present_set = set(present)
            cur.executemany(
                "INSERT INTO attendance (class_session_id, student_id, present) VALUES (%s, %s, %s)",
                [(sid, s, s in present_set) for s in sorted(active)])
            cur.executemany(
                "INSERT INTO class_turn (class_session_id, turn_no, team_id, question_id) VALUES (%s, %s, %s, %s)",
                [(sid, n + 1, team_ids[n % len(team_ids)], queue[n]) for n in range(total)])
        return _state(conn, sid)


@router.get("/sessions/{session_id}")
def get_session(session_id: UUID):
    with db.connection() as conn:
        return _state(conn, session_id)


@router.put("/sessions/{session_id}/teams")
def put_teams(session_id: UUID, body: TeamsIn):
    with db.connection() as conn:
        sess = _get_session_row(conn, session_id, lock=True)
        if sess["status"] != "live":
            raise HTTPException(409, "Session already finished")
        if sess["grouping"] == INDIVIDUAL:
            raise HTTPException(409, "Individual sessions have no teams to edit")
        if conn.execute("SELECT 1 FROM class_attempt WHERE class_session_id = %s LIMIT 1",
                        (session_id,)).fetchone():
            raise HTTPException(409, "Teams can only be changed before the first attempt")
        team_ids = {r["id"] for r in conn.execute(
            "SELECT id FROM team WHERE class_session_id = %s", (session_id,)).fetchall()}
        given = [t.team_id for t in body.teams]
        if len(set(given)) != len(given) or set(given) != team_ids:
            raise HTTPException(422, "teams must list every team of this session exactly once")
        present = {r["student_id"] for r in conn.execute(
            "SELECT student_id FROM attendance WHERE class_session_id = %s AND present",
            (session_id,)).fetchall()}
        all_ids = [s for t in body.teams for s in t.student_ids]
        if len(set(all_ids)) != len(all_ids):
            raise HTTPException(422, "a student can be in only one team")
        if set(all_ids) != present:
            raise HTTPException(422, "teams must contain exactly the present students")
        conn.execute("DELETE FROM team_member WHERE team_id = ANY(%s)", (list(team_ids),))
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO team_member (team_id, student_id) VALUES (%s, %s)",
                            [(t.team_id, s) for t in body.teams for s in t.student_ids])
        return _state(conn, session_id)


@router.post("/sessions/{session_id}/students")
def add_late_students(session_id: UUID, body: LateStudentsIn):
    """Late arrivals (both groupings), only while the session is live (409 once finished).
    Each name: trimmed + inner whitespace collapsed; matched case-insensitively against the classroom roster.
    New name -> new student. Existing active student not yet present -> marked present. Already present,
    inactive, or > 100 chars -> `skipped`. In-paste duplicates are dropped silently.
    individual: a team row per newcomer (next position); teams: into the currently smallest team."""
    with db.connection() as conn:
        # Same lock as attempt / next / skip (session row), so a late add serialises with them.
        sess = _get_session_row(conn, session_id, lock=True)
        if sess["status"] != "live":
            raise HTTPException(409, "Session already finished")
        individual = sess["grouping"] == INDIVIDUAL
        cid = sess["classroom_id"]
        # Classroom lock: same as the roster bulk-add, so the unique (classroom_id, name) can't race.
        conn.execute("SELECT 1 FROM classroom WHERE id = %s FOR UPDATE", (cid,))
        roster = {r["name"].lower(): r for r in conn.execute(
            "SELECT id, name, is_active FROM student WHERE classroom_id = %s", (cid,)).fetchall()}
        present = {r["student_id"] for r in conn.execute(
            "SELECT student_id FROM attendance WHERE class_session_id = %s AND present", (session_id,)).fetchall()}
        seen: set[str] = set()
        added, skipped = [], []
        for raw in body.names:
            name = " ".join(str(raw).split())
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            ex = roster.get(key)
            if len(name) > 100 or (ex is not None and (not ex["is_active"] or ex["id"] in present)):
                skipped.append(name)
                continue
            if individual and len(present) >= MAX_INDIVIDUAL_STUDENTS:
                raise HTTPException(422, f"An individual session holds at most {MAX_INDIVIDUAL_STUDENTS} "
                                         "present students")
            if ex is None:
                ex = conn.execute("INSERT INTO student (classroom_id, name) VALUES (%s, %s) "
                                  "RETURNING id, name, is_active", (cid, name)).fetchone()
                roster[key] = ex
                new_student = True
            else:
                new_student = False
            stud = ex["id"]
            conn.execute(
                """INSERT INTO attendance (class_session_id, student_id, present) VALUES (%s, %s, true)
                   ON CONFLICT (class_session_id, student_id) DO UPDATE SET present = true""",
                (session_id, stud))
            present.add(stud)
            if individual:
                pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 AS p FROM team "
                                   "WHERE class_session_id = %s", (session_id,)).fetchone()["p"]
                team_id = _insert_individual_team(conn, session_id, pos, ex["name"])
            else:
                team_id = conn.execute(
                    """SELECT t.id FROM team t LEFT JOIN team_member tm ON tm.team_id = t.id
                        WHERE t.class_session_id = %s GROUP BY t.id, t.position
                        ORDER BY COUNT(tm.student_id), t.position LIMIT 1""", (session_id,)).fetchone()["id"]
            conn.execute("INSERT INTO team_member (team_id, student_id) VALUES (%s, %s)", (team_id, stud))
            added.append({"student_id": stud, "name": ex["name"], "team_id": team_id, "new_student": new_student})
        return {"added": added, "skipped": skipped, "state": _state(conn, session_id)}


def _check_attempts_left(used: int, game_mode: str) -> None:
    if game_mode != MC:
        raise HTTPException(422, SPEAKING_UNSUPPORTED)  # a legacy speaking turn: the teacher skips it
    if used >= MC_MAX_ATTEMPTS:
        raise HTTPException(409, "one attempt for quiz")


def _precheck_attempt(sid: UUID, turn_no: int, student_id: int) -> dict:
    """Cheap checks before scoring (the authoritative checks run again under lock). Returns the question."""
    with db.connection() as conn:
        sess = _get_session_row(conn, sid)
        turn = conn.execute("SELECT * FROM class_turn WHERE class_session_id = %s AND turn_no = %s",
                            (sid, turn_no)).fetchone()
        if not turn:
            raise HTTPException(404, f"Turn {turn_no} not found")
        if sess["status"] != "live":
            raise HTTPException(409, "Session already finished")
        if sess["current_turn"] != turn_no:
            raise HTTPException(409, f"Turn {turn_no} is not the current turn ({sess['current_turn']})")
        q = conn.execute("SELECT game_mode, options FROM question WHERE id = %s",
                         (turn["question_id"],)).fetchone()
        used = conn.execute("SELECT COUNT(*)::int AS n FROM class_attempt WHERE class_session_id = %s "
                            "AND turn_no = %s", (sid, turn_no)).fetchone()["n"]
        _check_attempts_left(used, q["game_mode"])
        _check_attempt_student(conn, sid, sess, turn, used, student_id)
        return q


def _check_attempt_student(conn, sid: UUID, sess: dict, turn: dict, used: int, student_id: int) -> int:
    """422 if the student may not answer this turn; returns the team the attempt is credited to.
    teams: a present member of the turn's team. individual: ANY present student — but once a turn has an
    attempt it belongs to that student (anyone else -> 409)."""
    if sess["grouping"] != INDIVIDUAL:
        if not _is_present_member(conn, sid, turn["team_id"], student_id):
            raise HTTPException(422, "Student is not a present member of this turn's team")
        return turn["team_id"]
    team_id = _individual_team_id(conn, sid, student_id)
    if team_id is None:
        raise HTTPException(422, "Student is not present in this session")
    if used and turn["student_id"] is not None and turn["student_id"] != student_id:
        raise HTTPException(409, "This turn was already answered by another student")
    return team_id


def _record_attempt(sid: UUID, turn_no: int, student_id: int, duration_ms: int, choice: int) -> dict:
    with db.connection() as conn:
        sess, turn = _lock_current_turn(conn, sid, turn_no)
        q = conn.execute("SELECT game_mode, difficulty, base_points, time_limit_sec, "
                         "correct_option, options FROM question WHERE id = %s", (turn["question_id"],)).fetchone()
        used = conn.execute("SELECT COUNT(*)::int AS n FROM class_attempt WHERE class_session_id = %s "
                            "AND turn_no = %s", (sid, turn_no)).fetchone()["n"]
        _check_attempts_left(used, q["game_mode"])
        team_id = _check_attempt_student(conn, sid, sess, turn, used, student_id)
        old_team_id = turn["team_id"]
        if team_id != old_team_id:
            # individual: re-point the turn to the credited student's team (same tx, under the turn lock)
            conn.execute("UPDATE class_turn SET team_id = %s WHERE class_session_id = %s AND turn_no = %s",
                         (team_id, sid, turn_no))

        result = scoring.score_multiple_choice(choice, q["correct_option"])
        # safe to reveal: a quiz turn allows exactly one attempt
        opts = list(q["options"] or [])
        co = q["correct_option"]
        result["feedback"]["correct_option"] = co
        result["feedback"]["correct_option_text"] = opts[co] if co is not None and 0 <= co < len(opts) else None
        # Team streak: previous turns of this team.
        prior = _streak_from(_team_turn_history(conn, team_id, before_turn=turn_no))
        streak = scoring.next_streak(prior, result["passed"])
        pts = scoring.compute_points(
            base_points=q["base_points"], difficulty=q["difficulty"], accuracy=result["accuracy"],
            passed=result["passed"], streak=streak, duration_ms=duration_ms,
            time_limit_sec=q["time_limit_sec"])
        attempt_no = used + 1
        conn.execute(
            """INSERT INTO class_attempt (class_session_id, turn_no, attempt_no, student_id, transcript,
                                          accuracy, passed, stars, points, duration_ms, feedback)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (sid, turn_no, attempt_no, student_id, "", result["accuracy"], result["passed"],
             result["stars"], pts["points"], duration_ms,
             Jsonb({**result["feedback"], "streak": streak})),
        )
        # best_points = max over attempts; the turn is credited to the student of the best attempt.
        best = conn.execute(
            """SELECT points, student_id FROM class_attempt WHERE class_session_id = %s AND turn_no = %s
                ORDER BY points DESC, attempt_no LIMIT 1""",
            (sid, turn_no),
        ).fetchone()
        conn.execute("UPDATE class_turn SET best_points = %s, student_id = %s "
                     "WHERE class_session_id = %s AND turn_no = %s",
                     (best["points"], best["student_id"], sid, turn_no))
        team = _recompute_team(conn, team_id)
        if old_team_id != team_id:
            _recompute_team(conn, old_team_id)
        state = _state(conn, sid)
    return {
        "attempt_no": attempt_no,
        "transcript": "",
        "accuracy": result["accuracy"],
        "passed": result["passed"],
        "stars": result["stars"],
        "points": pts["points"],
        "streak": streak,
        "streak_multiplier": pts["streak_multiplier"],
        "speed_bonus": pts["speed_bonus"],
        "feedback": result["feedback"],
        "turn": {"turn_no": turn_no, "status": "pending", "best_points": best["points"],
                 "attempts_left": MC_MAX_ATTEMPTS - attempt_no},
        "team": {"id": team["id"], "score": team["score"], "streak": team["streak"]},
        "state": state,
    }


@router.post("/sessions/{session_id}/turns/{turn_no}/attempts")
async def create_attempt(
    session_id: UUID,
    turn_no: int,
    student_id: int = Form(...),
    duration_ms: int = Form(0, ge=0, le=10 * 60 * 1000),
    audio: Optional[UploadFile] = File(None),
    choice: Optional[int] = Form(None),
):
    """multiple_choice turn: form field `choice` (0-based). An `audio` upload (speaking) is rejected with 422."""
    if audio is not None:
        raise HTTPException(422, SPEAKING_UNSUPPORTED)
    q = await run_in_threadpool(_precheck_attempt, session_id, turn_no, student_id)
    n = len(q["options"] or [])
    if choice is None or not 0 <= choice < n:
        raise HTTPException(422, f"choice: required for a quiz turn, 0..{n - 1}")
    return await run_in_threadpool(_record_attempt, session_id, turn_no, student_id, duration_ms, choice)


def _advance(conn, sid: UUID) -> None:
    conn.execute("UPDATE class_session SET current_turn = current_turn + 1 WHERE id = %s", (sid,))


@router.post("/sessions/{session_id}/turns/{turn_no}/next")
def next_turn(session_id: UUID, turn_no: int):
    """Resolve the current turn and advance. Attempted -> done; not attempted -> skipped (0 points)."""
    with db.connection() as conn:
        sess, turn = _lock_current_turn(conn, session_id, turn_no)
        attempted = conn.execute("SELECT 1 FROM class_attempt WHERE class_session_id = %s AND turn_no = %s "
                                 "LIMIT 1", (session_id, turn_no)).fetchone() is not None
        conn.execute("UPDATE class_turn SET status = %s WHERE class_session_id = %s AND turn_no = %s",
                     ("done" if attempted else "skipped", session_id, turn_no))
        if sess["grouping"] == INDIVIDUAL and not attempted:
            # nobody answered: the turn is charged to the suggested student (so the rotation moves on)
            stud, team_id = _individual_suggestion(conn, session_id, turn)
            _credit_turn(conn, session_id, turn, stud, team_id)
        _recompute_team(conn, turn["team_id"])
        _advance(conn, session_id)
        return _state(conn, session_id)


def _credit_turn(conn, sid: UUID, turn: dict, student_id: Optional[int], team_id: Optional[int]) -> None:
    """Individual mode: set the turn's student and re-point its team (caller holds the session + turn lock);
    recomputes the new team (the caller recomputes the old one)."""
    if student_id is None or team_id is None:
        return
    conn.execute("UPDATE class_turn SET student_id = %s, team_id = %s WHERE class_session_id = %s AND turn_no = %s",
                 (student_id, team_id, sid, turn["turn_no"]))
    if team_id != turn["team_id"]:
        _recompute_team(conn, team_id)


@router.post("/sessions/{session_id}/turns/{turn_no}/skip")
def skip_turn(session_id: UUID, turn_no: int, body: Optional[SkipIn] = None):
    body = body or SkipIn()
    with db.connection() as conn:
        sess, turn = _lock_current_turn(conn, session_id, turn_no)
        if conn.execute("SELECT 1 FROM class_attempt WHERE class_session_id = %s AND turn_no = %s LIMIT 1",
                        (session_id, turn_no)).fetchone():
            raise HTTPException(409, "Turn already has an attempt — use next to keep its points")
        individual = sess["grouping"] == INDIVIDUAL
        if individual:
            if body.student_id is not None:
                team_id = _individual_team_id(conn, session_id, body.student_id)
                if team_id is None:
                    raise HTTPException(422, "Student is not present in this session")
                stud = body.student_id
            else:
                stud, team_id = _individual_suggestion(conn, session_id, turn)
        elif body.student_id is not None and not _is_present_member(conn, session_id, turn["team_id"],
                                                                    body.student_id):
            raise HTTPException(422, "Student is not a present member of this turn's team")
        conn.execute("""UPDATE class_turn SET status = 'skipped', best_points = 0, student_id = %s
                         WHERE class_session_id = %s AND turn_no = %s""",
                     (body.student_id, session_id, turn_no))
        if individual:
            _credit_turn(conn, session_id, turn, stud, team_id)
        _recompute_team(conn, turn["team_id"])
        _advance(conn, session_id)
        return _state(conn, session_id)


def _student_participation(conn, sid: UUID) -> list[dict]:
    rows = conn.execute(
        """SELECT s.id AS student_id, s.name, a.present, t.name AS team, t.id AS team_id,
                  (SELECT COUNT(DISTINCT x.turn_no) FROM (
                       SELECT turn_no FROM class_turn WHERE class_session_id = %(s)s AND student_id = s.id
                       UNION SELECT turn_no FROM class_attempt WHERE class_session_id = %(s)s AND student_id = s.id
                   ) x)::int AS turns,
                  (SELECT COUNT(*) FROM class_attempt ca
                    WHERE ca.class_session_id = %(s)s AND ca.student_id = s.id)::int AS attempts,
                  (SELECT MAX(accuracy) FROM class_attempt ca
                    WHERE ca.class_session_id = %(s)s AND ca.student_id = s.id) AS best_accuracy,
                  (SELECT ROUND(AVG(accuracy), 2) FROM class_attempt ca
                    WHERE ca.class_session_id = %(s)s AND ca.student_id = s.id) AS avg_accuracy,
                  (SELECT COALESCE(SUM(best_points), 0) FROM class_turn ct
                    WHERE ct.class_session_id = %(s)s AND ct.student_id = s.id)::int AS points
             FROM attendance a
             JOIN student s ON s.id = a.student_id
        LEFT JOIN (team_member tm JOIN team t ON t.id = tm.team_id AND t.class_session_id = %(s)s)
               ON tm.student_id = s.id
            WHERE a.class_session_id = %(s)s
            ORDER BY a.present DESC, t.position NULLS LAST, lower(s.name), s.id""",
        {"s": sid},
    ).fetchall()
    out = [_row(r) for r in rows]
    grouping = conn.execute('SELECT "grouping" FROM class_session WHERE id = %s', (sid,)).fetchone()
    if grouping and grouping["grouping"] == INDIVIDUAL:
        # the "team" is the student themself: no team label; present first, then by name
        for r in out:
            r["team"] = None
        out.sort(key=lambda r: (not r["present"], r["name"].lower(), r["student_id"]))
    return out


@router.post("/sessions/{session_id}/finish")
def finish_session(session_id: UUID):
    with db.connection() as conn:
        _get_session_row(conn, session_id, lock=True)
        conn.execute("""UPDATE class_session SET status = 'finished', finished_at = COALESCE(finished_at, now())
                         WHERE id = %s""", (session_id,))
        state = _state(conn, session_id)
        students = _student_participation(conn, session_id)
        ranking_rows = _leaderboard_entries(*_teams_and_members(conn, session_id))

    individual = state["grouping"] == INDIVIDUAL
    if individual:
        # per-student ranking: every present student (not only the top 10 of the leaderboard)
        ranking = [{"student_id": e["student_id"], "team_id": e["team_id"], "name": e["name"], "emoji": e["emoji"],
                    "color": e["color"], "score": e["score"], "rank": e["rank"]} for e in ranking_rows]
    else:
        teams = sorted(state["teams"], key=lambda t: (-t["score"], t["position"]))
        ranking, prev_score, rank = [], None, 0
        for i, t in enumerate(teams, start=1):
            if t["score"] != prev_score:
                rank, prev_score = i, t["score"]  # competition ranking: ties share a rank (1, 1, 3)
            ranking.append({"team_id": t["id"], "name": t["name"], "emoji": t["emoji"], "score": t["score"],
                            "rank": rank})

    scorers = [s for s in students if s["points"] > 0]
    mvp = None
    if scorers:
        top = sorted(scorers, key=lambda s: (-s["points"], -(s["best_accuracy"] or 0), s["name"].lower()))[0]
        mvp = {"student_id": top["student_id"], "name": top["name"], "team_id": top["team_id"],
               "points": top["points"]}
    part = state["participation"]
    return {
        "state": state,
        "ranking": ranking,
        "mvp": mvp,
        "participation": {**part, "students": [
            {k: s[k] for k in ("student_id", "name", "team", "present", "turns", "attempts",
                               "best_accuracy", "points")} for s in students]},
    }


@router.get("/sessions/{session_id}/participation.csv")
def participation_csv(session_id: UUID):
    with db.connection() as conn:
        meta = conn.execute(
            """SELECT c.name, c.school, c.program, cs.started_at FROM class_session cs
                 JOIN classroom c ON c.id = cs.classroom_id WHERE cs.id = %s""",
            (session_id,),
        ).fetchone()
        if not meta:
            raise HTTPException(404, "Class session not found")
        students = _student_participation(conn, session_id)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["school", "classroom", "program", "date", "student", "team", "present", "spoke", "turns",
                "points", "avg_accuracy"])
    day = meta["started_at"].date().isoformat()
    for s in students:
        w.writerow([meta["school"], meta["name"], meta["program"], day, s["name"], s["team"] or "",
                    "yes" if s["present"] else "no", "yes" if s["attempts"] > 0 else "no", s["turns"],
                    s["points"], "" if s["avg_accuracy"] is None else s["avg_accuracy"]])
    # BOM so Excel opens UTF-8 (Malay / emoji names) correctly.
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="participation-{day}-{session_id}.csv"'})


# --------------------------------------------------------------------------- reports

@router.get("/reports/participation")
def participation_report(program: Optional[str] = None,
                         from_: Optional[date] = Query(default=None, alias="from"),
                         to: Optional[date] = None):
    prog = (program or "").strip() or None
    params = {"prog": prog, "from": from_, "to": to}
    base = """FROM class_session cs JOIN classroom c ON c.id = cs.classroom_id
              WHERE (%(prog)s::text IS NULL OR lower(c.program) = lower(%(prog)s::text))
                AND (%(from)s::date IS NULL OR cs.started_at::date >= %(from)s::date)
                AND (%(to)s::date IS NULL OR cs.started_at::date <= %(to)s::date)"""
    with db.connection() as conn:
        tot = conn.execute(
            f"""WITH ss AS (SELECT cs.id, cs.classroom_id {base})
                SELECT (SELECT COUNT(*) FROM ss)::int AS sessions,
                       (SELECT COUNT(DISTINCT classroom_id) FROM ss)::int AS classrooms,
                       (SELECT COUNT(DISTINCT a.student_id) FROM attendance a JOIN ss ON ss.id = a.class_session_id
                         WHERE a.present)::int AS unique_students_present,
                       (SELECT COUNT(DISTINCT ca.student_id) FROM class_attempt ca
                          JOIN ss ON ss.id = ca.class_session_id)::int AS unique_students_spoke""",
            params,
        ).fetchone()
        by = conn.execute(
            f"""WITH ss AS (SELECT cs.id, cs.classroom_id {base})
                SELECT c.id AS classroom_id, c.name, c.school, c.program,
                       COUNT(DISTINCT ss.id)::int AS sessions,
                       (SELECT COUNT(DISTINCT a.student_id) FROM attendance a
                          JOIN ss s2 ON s2.id = a.class_session_id
                         WHERE s2.classroom_id = c.id AND a.present)::int AS present,
                       (SELECT COUNT(DISTINCT ca.student_id) FROM class_attempt ca
                          JOIN ss s2 ON s2.id = ca.class_session_id WHERE s2.classroom_id = c.id)::int AS spoke
                  FROM ss JOIN classroom c ON c.id = ss.classroom_id
                 GROUP BY c.id ORDER BY c.name, c.id""",
            params,
        ).fetchall()
    return {**tot, "by_classroom": by}
