"""Teacher-owned quizzes — /api/live/quizzes. See CONTRACT.md "Live — implementation notes" › Teacher quizzes.

There is no admin page any more: a teacher creates a quiz (a `question_pack` row) from the host flow and gets
an **edit key** (32-byte urlsafe secret) back once. Only sha256(edit key) is stored (`question_pack.edit_key_hash`,
db/010_teacher_quiz.sql). Every edit sends `X-Edit-Key`; the stored hash is compared with
`secrets.compare_digest`. Seeded packs have no key (read-only) — teachers `duplicate` them to customise.

Questions are multiple_choice only. Edits that touch a quiz's question list (add / delete / reorder) lock the pack
row (`FOR UPDATE`), so a reorder and a delete on the same quiz serialise; the reorder then sees the new list and
answers 422 if its id list is stale.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from typing import Any, Literal, Optional

import psycopg
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator, model_validator

from . import db, live, scoring

router = APIRouter(prefix="/api/live/quizzes", tags=["quizzes"])

MC = scoring.MULTIPLE_CHOICE
create_limiter = live.RateLimiter(int(os.environ.get("QUIZ_CREATE_LIMIT", "20")),
                                  float(os.environ.get("QUIZ_CREATE_WINDOW_SEC", "3600")))
_SPACE_RE = re.compile(r"\s+")
_schema_ready = False

Q_COLS = "id, prompt, options, correct_option, time_limit_sec, base_points, sort_order, image_url, image_alt"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def schema_ready(conn) -> bool:
    """db/010 applied? (cached once true). Lets the app run on a DB that has not been migrated yet."""
    global _schema_ready
    if not _schema_ready:
        _schema_ready = conn.execute(
            """SELECT COUNT(*) = 2 AS ok FROM information_schema.columns
                WHERE table_name = 'question_pack' AND column_name IN ('edit_key_hash', 'owner_label')"""
        ).fetchone()["ok"]
    return _schema_ready


def _require_schema(conn) -> None:
    if not schema_ready(conn):
        raise HTTPException(503, "Teacher quizzes need db/010_teacher_quiz.sql (run scripts/dev_db.sh)")


def split_keys(raw: Optional[str]) -> list[str]:
    return [k.strip() for k in (raw or "").split(",") if k.strip()][:50]


def _clean(v: Optional[str]) -> str:
    return _SPACE_RE.sub(" ", v or "").strip()


# --------------------------------------------------------------------------- models

class QuizIn(BaseModel):
    name: str = Field(max_length=100)
    description: Optional[str] = Field(default="", max_length=1000)
    topic: Literal["general", "ai"] = "general"
    owner_label: Optional[str] = Field(default="", max_length=100)  # e.g. "Cikgu Ana, SK Taman Desa"

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = _clean(v)
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("description", "owner_label")
    @classmethod
    def _txt(cls, v: Optional[str]) -> str:
        return (v or "").strip()


class QuizQuestionIn(BaseModel):
    prompt: str = Field(max_length=500)
    options: list[str]
    correct_option: int
    time_limit_sec: int = Field(default=20, ge=5, le=120)
    points: Literal[100, 200] = 100  # 200 = "double points"
    image_url: Optional[str] = Field(default=None, max_length=1000)
    image_alt: Optional[str] = Field(default=None, max_length=300)

    @field_validator("prompt")
    @classmethod
    def _prompt(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be blank")
        return v

    @field_validator("image_url", "image_alt")
    @classmethod
    def _blank(cls, v: Optional[str]) -> Optional[str]:
        return (v or "").strip() or None

    @model_validator(mode="after")
    def _opts(self) -> "QuizQuestionIn":
        opts = [str(o).strip() for o in self.options]
        if not 2 <= len(opts) <= 4 or any(not o or len(o) > 200 for o in opts):
            raise ValueError("options: 2-4 non-empty options (max 200 chars each)")
        if len({o.casefold() for o in opts}) != len(opts):
            raise ValueError("options must be different from each other")
        if not 0 <= self.correct_option < len(opts):
            raise ValueError(f"correct_option must be 0..{len(opts) - 1}")
        self.options = opts
        return self


class OrderIn(BaseModel):
    question_ids: list[int]


# --------------------------------------------------------------------------- helpers

def _pack_row(conn, pack_id: int, lock: bool = False) -> dict:
    row = conn.execute(
        "SELECT id, slug, name, topic, description, why_it_matters, is_active, created_at, edit_key_hash, "
        "owner_label FROM question_pack WHERE id = %s" + (" FOR UPDATE" if lock else ""), (pack_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Quiz not found")
    return row


def _key_ok(row: dict, key: Optional[str]) -> bool:
    stored = row.get("edit_key_hash")
    # always run one compare so a seeded pack (no key) and a wrong key take the same path
    return secrets.compare_digest((stored or "-").encode(), hash_key(key or "").encode()) and bool(stored and key)


def _editable(conn, pack_id: int, key: Optional[str], lock: bool = False) -> dict:
    _require_schema(conn)
    row = _pack_row(conn, pack_id, lock)
    if not _key_ok(row, key):
        raise HTTPException(403, "Invalid or missing X-Edit-Key" if row["edit_key_hash"]
                            else "This quiz is read-only; duplicate it to edit")
    return row


def _question_out(q: dict) -> dict:
    return {"id": q["id"], "prompt": q["prompt"], "options": list(q["options"]),
            "correct_option": q["correct_option"], "time_limit_sec": q["time_limit_sec"],
            "points": q["base_points"], "sort_order": q["sort_order"], "image_url": q["image_url"],
            "image_alt": q["image_alt"]}


def _quiz_out(conn, row: dict) -> dict:
    qs = conn.execute(
        f"""SELECT {Q_COLS} FROM question
             WHERE pack_id = %s AND is_active AND game_mode = 'multiple_choice'
             ORDER BY sort_order, id""", (row["id"],)).fetchall()
    return {"id": row["id"], "pack_id": row["id"], "name": row["name"], "description": row["description"],
            "topic": row["topic"], "owner_label": row["owner_label"] or "", "created_at": row["created_at"],
            "editable": True, "questions": [_question_out(q) for q in qs]}


def _new_pack(conn, name: str, description: str, topic: str, owner_label: str) -> tuple[int, str]:
    key = secrets.token_urlsafe(32)
    for _ in range(5):
        try:
            with conn.transaction():
                pid = conn.execute(
                    """INSERT INTO question_pack (slug, name, topic, description, why_it_matters, edit_key_hash,
                                                  owner_label)
                       VALUES (%s, %s, %s, %s, '', %s, %s) RETURNING id""",
                    (f"quiz-{secrets.token_hex(6)}", name, topic, description, hash_key(key), owner_label),
                ).fetchone()["id"]
            return pid, key
        except psycopg.errors.UniqueViolation:
            continue
    raise HTTPException(503, "Could not create the quiz, try again")


def list_packs_for(keys: list[str]) -> list[dict]:
    """GET /api/live/packs body: seeded packs (editable false) + the teacher quizzes whose key is supplied."""
    with db.connection() as conn:
        ready = schema_ready(conn)
        hashes = [hash_key(k) for k in keys]
        if ready:
            packs = conn.execute(
                """SELECT id, slug, name, topic, description, why_it_matters, owner_label,
                          (edit_key_hash IS NOT NULL) AS teacher_owned,
                          (edit_key_hash IS NOT NULL AND edit_key_hash = ANY(%s)) AS editable
                     FROM question_pack
                    WHERE is_active AND (edit_key_hash IS NULL OR edit_key_hash = ANY(%s))
                    ORDER BY (edit_key_hash IS NULL), topic, name, id""", (hashes, hashes)).fetchall()
        else:
            packs = conn.execute(
                """SELECT id, slug, name, topic, description, why_it_matters, '' AS owner_label,
                          false AS teacher_owned, false AS editable
                     FROM question_pack WHERE is_active ORDER BY topic, name, id""").fetchall()
        counts = conn.execute(
            f"""SELECT q.pack_id, q.game_mode, COUNT(*)::int AS n FROM question q
                 WHERE q.is_active AND q.pack_id IS NOT NULL AND {live.PLAYABLE_SQL}
                 GROUP BY q.pack_id, q.game_mode""").fetchall()
    by = {p["id"]: {MC: 0} for p in packs}  # PLAYABLE_SQL counts multiple_choice only
    for c in counts:
        if c["pack_id"] in by:
            by[c["pack_id"]][c["game_mode"]] = c["n"]
    return [{**p, "question_counts": by[p["id"]]} for p in packs]


# --------------------------------------------------------------------------- routes

@router.post("", status_code=201)
def create_quiz(body: QuizIn, request: Request):
    if not create_limiter.hit(live._client_ip(request)):
        raise HTTPException(429, "Too many quizzes created from this network, try again later")
    with db.connection() as conn:
        _require_schema(conn)
        pid, key = _new_pack(conn, body.name, body.description, body.topic, body.owner_label)
    return {"pack_id": pid, "edit_key": key}


@router.post("/{pack_id}/duplicate", status_code=201)
def duplicate_quiz(pack_id: int, request: Request, x_edit_key: Optional[str] = Header(default=None)):
    """Copy a seeded pack (no key needed) or your own quiz (key needed) with its active playable MC questions."""
    if not create_limiter.hit(live._client_ip(request)):
        raise HTTPException(429, "Too many quizzes created from this network, try again later")
    with db.connection() as conn:
        _require_schema(conn)
        src = _pack_row(conn, pack_id)
        if src["edit_key_hash"] and not _key_ok(src, x_edit_key):
            raise HTTPException(403, "Invalid or missing X-Edit-Key")
        if not src["is_active"]:
            raise HTTPException(404, "Quiz not found")
        name = (src["name"][:93] + " (copy)")
        pid, key = _new_pack(conn, name, src["description"], src["topic"], "")
        n = conn.execute(
            f"""INSERT INTO question (pack_id, game_mode, prompt, options, correct_option, time_limit_sec,
                                      base_points, difficulty, image_url, image_alt, sort_order, keywords)
                SELECT %s, 'multiple_choice', q.prompt, q.options, q.correct_option, q.time_limit_sec,
                       q.base_points, q.difficulty, q.image_url, q.image_alt,
                       ROW_NUMBER() OVER (ORDER BY q.sort_order, q.id), '{{}}'
                  FROM question q
                 WHERE q.pack_id = %s AND q.is_active AND q.game_mode = 'multiple_choice' AND {live.PLAYABLE_SQL}
                RETURNING id""", (pid, pack_id)).fetchall()
    return {"pack_id": pid, "edit_key": key, "question_count": len(n)}


@router.get("/{pack_id}")
def get_quiz(pack_id: int, x_edit_key: Optional[str] = Header(default=None)):
    with db.connection() as conn:
        return _quiz_out(conn, _editable(conn, pack_id, x_edit_key))


@router.put("/{pack_id}")
def update_quiz(pack_id: int, body: QuizIn, x_edit_key: Optional[str] = Header(default=None)):
    with db.connection() as conn:
        _editable(conn, pack_id, x_edit_key, lock=True)
        row = conn.execute(
            """UPDATE question_pack SET name = %s, description = %s, topic = %s, owner_label = %s WHERE id = %s
               RETURNING id, slug, name, topic, description, why_it_matters, is_active, created_at,
                         edit_key_hash, owner_label""",
            (body.name, body.description, body.topic, body.owner_label, pack_id)).fetchone()
        return _quiz_out(conn, row)


@router.post("/{pack_id}/questions", status_code=201)
def add_question(pack_id: int, body: QuizQuestionIn, x_edit_key: Optional[str] = Header(default=None)):
    with db.connection() as conn:
        _editable(conn, pack_id, x_edit_key, lock=True)
        nxt = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM question WHERE pack_id = %s "
                           "AND is_active", (pack_id,)).fetchone()["n"]
        q = conn.execute(
            f"""INSERT INTO question (pack_id, game_mode, prompt, options, correct_option, time_limit_sec,
                                      base_points, difficulty, image_url, image_alt, sort_order, keywords)
                VALUES (%s, 'multiple_choice', %s, %s, %s, %s, %s, 1, %s, %s, %s, '{{}}') RETURNING {Q_COLS}""",
            (pack_id, body.prompt, body.options, body.correct_option, body.time_limit_sec, body.points,
             body.image_url, body.image_alt, nxt)).fetchone()
    return _question_out(q)


def _own_question(conn, pack_id: int, qid: int, lock: bool = True) -> dict:
    q = conn.execute(
        f"SELECT {Q_COLS} FROM question WHERE id = %s AND pack_id = %s AND is_active "
        f"AND game_mode = 'multiple_choice'" + (" FOR UPDATE" if lock else ""), (qid, pack_id)).fetchone()
    if not q:
        raise HTTPException(404, "Question not found in this quiz")
    return q


@router.put("/{pack_id}/questions/{qid}")
def update_question(pack_id: int, qid: int, body: QuizQuestionIn, x_edit_key: Optional[str] = Header(default=None)):
    with db.connection() as conn:
        _editable(conn, pack_id, x_edit_key)
        _own_question(conn, pack_id, qid)
        q = conn.execute(
            f"""UPDATE question SET prompt = %s, options = %s, correct_option = %s, time_limit_sec = %s,
                       base_points = %s, image_url = %s, image_alt = %s, updated_at = now()
                 WHERE id = %s RETURNING {Q_COLS}""",
            (body.prompt, body.options, body.correct_option, body.time_limit_sec, body.points, body.image_url,
             body.image_alt, qid)).fetchone()
    return _question_out(q)


USED_SQL = """SELECT EXISTS (SELECT 1 FROM live_question WHERE question_id = %(q)s)
                  OR EXISTS (SELECT 1 FROM class_turn WHERE question_id = %(q)s)
                  OR EXISTS (SELECT 1 FROM attempt WHERE question_id = %(q)s)
                  OR EXISTS (SELECT 1 FROM class_attempt a JOIN class_turn t
                                ON t.class_session_id = a.class_session_id AND t.turn_no = a.turn_no
                              WHERE t.question_id = %(q)s)
                  OR (to_regclass('session_question') IS NOT NULL
                      AND EXISTS (SELECT 1 FROM session_question WHERE question_id = %(q)s)) AS used"""


@router.delete("/{pack_id}/questions/{qid}")
def delete_question(pack_id: int, qid: int, x_edit_key: Optional[str] = Header(default=None)):
    """Hard delete if the question was never played anywhere; otherwise archive (is_active = false) so
    reports keep working. Returns which one happened."""
    with db.connection() as conn:
        _editable(conn, pack_id, x_edit_key, lock=True)
        _own_question(conn, pack_id, qid)
        used = conn.execute(USED_SQL, {"q": qid}).fetchone()["used"]
        if not used:
            try:
                with conn.transaction():  # a game created at this very moment may reference it -> archive
                    conn.execute("DELETE FROM question WHERE id = %s", (qid,))
                return {"question_id": qid, "deleted": True, "archived": False}
            except psycopg.errors.ForeignKeyViolation:
                pass
        conn.execute("UPDATE question SET is_active = false, updated_at = now() WHERE id = %s", (qid,))
    return {"question_id": qid, "deleted": False, "archived": True}


@router.put("/{pack_id}/order")
def reorder(pack_id: int, body: OrderIn, x_edit_key: Optional[str] = Header(default=None)):
    """`question_ids` must list every active question of the quiz exactly once (else 422: reload and retry)."""
    with db.connection() as conn:
        row = _editable(conn, pack_id, x_edit_key, lock=True)
        current = [r["id"] for r in conn.execute(
            "SELECT id FROM question WHERE pack_id = %s AND is_active AND game_mode = 'multiple_choice'",
            (pack_id,)).fetchall()]
        if len(body.question_ids) != len(set(body.question_ids)) or set(body.question_ids) != set(current):
            raise HTTPException(422, "question_ids must list every question of this quiz exactly once")
        with conn.cursor() as cur:
            cur.executemany("UPDATE question SET sort_order = %s, updated_at = now() WHERE id = %s",
                            [(i + 1, qid) for i, qid in enumerate(body.question_ids)])
        return _quiz_out(conn, row)
