"""Program-team reports (/api/reports) across BOTH game kinds — see CONTRACT.md "REPORTS".

- live   = PIN games (live_game / live_player / live_answer); school from live_game.
- class  = one-screen team games (class_session / attendance / class_attempt); school from classroom.
- homework = self-paced PIN games (live_game.mode = 'self_paced').

Access: header `X-Reports-Key`, compared in constant time (sha256 digests + hmac.compare_digest) against env
`REPORTS_KEY`, which is REQUIRED: there is no default in code. Unset → every /api/reports/* call is 503
"reports not configured" and a warning is logged at startup. Wrong or missing key → 401; failed attempts are
rate limited per IP (in-memory, per process — Redis when scaling out).
In the monorepo this becomes a Better Auth session with a `program_manager` role.

Every query is read-only and parameterised: the SQL text is built only from constant fragments in this file;
user input is always a bound parameter. Every list is paginated (limit/offset) or capped.
"""
from __future__ import annotations

import collections
import csv
import hashlib
import io
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import date
from hmac import compare_digest as _compare
from typing import Any, Iterator, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response

from . import db

log = logging.getLogger("playclass")

NOT_SET = "(not set)"
COMPLETION_THRESHOLD = 0.8        # live: answered >= 80% of the questions the player was present for
CSV_MAX_ROWS = 10000              # ?format=csv exports the whole filtered list up to this cap
MATCH_NOTE = "Matched by name, approximate: players are anonymous nicknames, so the same name in one school is treated as one student."


NOT_CONFIGURED = "reports not configured"


def _expected_key() -> str:
    """The configured access code, or "" when REPORTS_KEY is unset / blank (reports are then disabled)."""
    return (os.environ.get("REPORTS_KEY") or "").strip()


def warn_if_not_configured() -> bool:
    if not _expected_key():
        log.warning("REPORTS_KEY is not set: /api/reports/* answers 503 %r until it is configured.", NOT_CONFIGURED)
        return True
    return False


warn_if_not_configured()  # imported once at app startup (and on every --reload)


# --------------------------------------------------------------------------- access key + failure rate limit

class FailLimiter:
    """Counts FAILED key attempts per IP in a sliding window. PROTOTYPE: per process (move to Redis)."""

    def __init__(self, limit: int, window_sec: float):
        self.limit, self.window = limit, window_sec
        self._hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def _trim(self, dq: collections.deque, now: float) -> None:
        while dq and now - dq[0] > self.window:
            dq.popleft()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits.get(key)
            if not dq:
                return False
            self._trim(dq, now)
            return len(dq) >= self.limit

    def record(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            self._trim(dq, now)
            dq.append(now)
            if len(self._hits) > 10000:  # crude memory bound
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    del self._hits[k]

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


fail_limiter = FailLimiter(int(os.environ.get("REPORTS_FAIL_LIMIT", "10")),
                           float(os.environ.get("REPORTS_FAIL_WINDOW_SEC", "300")))


def key_matches(given: Optional[str]) -> bool:
    """Constant time: both sides are hashed to 32 bytes first, so neither length nor content leaks via timing.
    The comparison runs even when the header is missing."""
    a = hashlib.sha256((given or "").encode("utf-8")).digest()
    b = hashlib.sha256(_expected_key().encode("utf-8")).digest()
    return _compare(a, b) and bool(given)


def require_reports_key(request: Request, x_reports_key: Optional[str] = Header(default=None)) -> None:
    if not _expected_key():
        raise HTTPException(503, NOT_CONFIGURED)
    ip = request.client.host if request.client else "unknown"  # X-Forwarded-For not trusted (see live.py)
    if fail_limiter.blocked(ip):
        raise HTTPException(429, "Too many wrong access codes. Wait a few minutes and try again.")
    if not key_matches(x_reports_key):
        fail_limiter.record(ip)
        raise HTTPException(401, "Reports access code required" if not x_reports_key else "Wrong reports access code")


router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(require_reports_key)])
# Key-free probe for the /reports page: 503 "reports not configured" when REPORTS_KEY is unset, else 200. It never
# checks a code, so opening the page does not count as a failed attempt.
status_router = APIRouter(prefix="/api/reports", tags=["reports"])


@status_router.get("/status")
def reports_status() -> dict:
    if not _expected_key():
        raise HTTPException(503, NOT_CONFIGURED)
    return {"configured": True}


# --------------------------------------------------------------------------- SQL building blocks (constants only)

def _where(at: str, school: str, program: str) -> str:
    """Filter fragment for one branch. Column names are constants from this file; values are bound params."""
    return f"""(%(prog)s::text IS NULL OR lower(btrim({program})) = %(prog)s::text)
           AND (%(school_like)s::text IS NULL OR btrim({school}) ILIKE %(school_like)s::text)
           AND (%(school_key)s::text IS NULL OR lower(btrim({school})) = %(school_key)s::text)
           AND (%(from)s::date IS NULL OR {at} >= %(from)s::date)
           AND (%(to)s::date IS NULL OR {at} < %(to)s::date + 1)"""


# ss = one row per session matching the filters. kind: 'live' (PIN game, teacher-paced), 'homework'
# (live_game.mode = 'self_paced', db/012) or 'class' (one-screen team game).
LIVE_KIND = "(CASE WHEN g.mode = 'self_paced' THEN 'homework' ELSE 'live' END)"
SS = f"""ss AS (
  SELECT {LIVE_KIND}::text AS kind, g.id, g.title, g.teacher_name, btrim(g.school) AS school,
         btrim(g.program) AS program, g.created_at AS at,
         -- effective status: homework closes lazily, so a past deadline counts as ended even if not yet written
         CASE WHEN g.status = 'ended' OR (g.mode = 'self_paced' AND g.closes_at IS NOT NULL AND g.closes_at <= now())
              THEN 'ended' ELSE g.status END AS status,
         CASE WHEN g.mode = 'self_paced' THEN (SELECT COUNT(*)::int FROM live_question lq WHERE lq.game_id = g.id)
              WHEN g.status = 'lobby' THEN 0 ELSE g.current_index + 1 END AS played,
         NULL::boolean AS done, NULL::text AS grouping
    FROM live_game g
   WHERE (%(kind)s::text IS NULL OR {LIVE_KIND} = %(kind)s::text) AND (%(sid)s::uuid IS NULL OR g.id = %(sid)s::uuid)
     AND {_where('g.created_at', 'g.school', 'g.program')}
  UNION ALL
  SELECT 'class'::text, cs.id, c.name, c.teacher_name, btrim(c.school), btrim(c.program),
         cs.started_at, cs.status,
         (SELECT COUNT(*)::int FROM class_turn t WHERE t.class_session_id = cs.id),
         (cs.status = 'finished' OR NOT EXISTS (SELECT 1 FROM class_turn t
                                                 WHERE t.class_session_id = cs.id AND t.status = 'pending')),
         cs.grouping
    FROM class_session cs JOIN classroom c ON c.id = cs.classroom_id
   WHERE (%(kind)s::text IS NULL OR %(kind)s::text = 'class') AND (%(sid)s::uuid IS NULL OR cs.id = %(sid)s::uuid)
     AND {_where('cs.started_at', 'c.school', 'c.program')}
)"""

# pp = one row per participation (a person in a session). Set-based (no per-player subqueries):
#   live     : every non-kicked player. present_for = questions played minus the questions that had already
#              closed when the player joined (a LATER question already had its first answer before joined_at),
#              never less than what they answered. completed = answered >= 80% of present_for (present_for > 0).
#   homework : every non-kicked player; completed = live_player.finished_at IS NOT NULL (reached the end).
#   class    : every PRESENT student. answered/correct/accuracy per TURN (best attempt of the turn by that
#              student). completed = took >= 1 turn AND the session was completed (finished, or no pending turn).
PP = """lg_ids AS (SELECT id FROM ss WHERE kind IN ('live', 'homework')),
la AS (SELECT x.player_id, COUNT(*)::int AS answered, COUNT(*) FILTER (WHERE x.passed)::int AS correct,
              SUM(x.accuracy) AS acc_sum
         FROM live_answer x WHERE x.game_id IN (SELECT id FROM lg_ids) GROUP BY x.player_id),
lq AS (SELECT x.game_id, x.idx, MIN(x.created_at) AS first_at
         FROM live_answer x WHERE x.game_id IN (SELECT id FROM ss WHERE kind = 'live') GROUP BY 1, 2),
lpre AS (SELECT p.id AS player_id, MAX(lq.idx) AS mx
           FROM lq JOIN live_player p ON p.game_id = lq.game_id AND lq.first_at < p.joined_at GROUP BY p.id),
cs_ids AS (SELECT id FROM ss WHERE kind = 'class'),
cb AS (SELECT t.class_session_id AS sid, t.student_id, COUNT(*)::int AS answered,
              COUNT(*) FILTER (WHERE t.passed)::int AS correct, SUM(t.best) AS acc_sum
         FROM (SELECT ca.class_session_id, ca.student_id, ca.turn_no, MAX(ca.accuracy) AS best,
                      bool_or(ca.passed) AS passed
                 FROM class_attempt ca WHERE ca.class_session_id IN (SELECT id FROM cs_ids) GROUP BY 1, 2, 3) t
        GROUP BY 1, 2),
cpts AS (SELECT ct.class_session_id AS sid, ct.student_id, SUM(ct.best_points)::int AS score
           FROM class_turn ct WHERE ct.class_session_id IN (SELECT id FROM cs_ids) AND ct.student_id IS NOT NULL
          GROUP BY 1, 2),
lp AS (SELECT s.kind, s.id AS sid, s.school, s.program, s.at, s.title, 'l' || p.id::text AS person,
              p.id AS person_id, p.nickname AS name, COALESCE(la.answered, 0) AS answered,
              COALESCE(la.correct, 0) AS correct, COALESCE(la.acc_sum, 0) AS acc_sum, p.score, p.finished_at,
              p.current_idx,
              GREATEST(s.played - CASE WHEN s.kind = 'live' THEN COALESCE(lpre.mx, 0) ELSE 0 END,
                       COALESCE(la.answered, 0)) AS present_for
         FROM ss s
         JOIN live_player p ON p.game_id = s.id AND NOT p.is_kicked
         LEFT JOIN la ON la.player_id = p.id
         LEFT JOIN lpre ON lpre.player_id = p.id
        WHERE s.kind IN ('live', 'homework')),
pp AS (
  SELECT kind, sid, school, program, at, title, person, person_id, name, answered, correct, acc_sum, score,
         present_for, finished_at, current_idx,
         CASE WHEN kind = 'homework' THEN finished_at IS NOT NULL
              ELSE present_for > 0 AND answered >= %(threshold)s::numeric * present_for END AS completed
    FROM lp
  UNION ALL
  SELECT s.kind, s.id, s.school, s.program, s.at, s.title, 'c' || st.id::text, st.id, st.name,
         COALESCE(cb.answered, 0), COALESCE(cb.correct, 0), COALESCE(cb.acc_sum, 0), COALESCE(cpts.score, 0),
         NULL::int, NULL::timestamptz, NULL::int, (COALESCE(cb.answered, 0) > 0 AND s.done)
    FROM ss s
    JOIN attendance at ON at.class_session_id = s.id AND at.present
    JOIN student st ON st.id = at.student_id
    LEFT JOIN cb ON cb.sid = s.id AND cb.student_id = st.id
    LEFT JOIN cpts ON cpts.sid = s.id AND cpts.student_id = st.id
   WHERE s.kind = 'class'
)"""

AGG = """COUNT(DISTINCT pp.person)::int AS participants,
         COUNT(DISTINCT pp.person) FILTER (WHERE pp.answered > 0)::int AS participated,
         COUNT(pp.person)::int AS joined,
         COUNT(pp.person) FILTER (WHERE pp.answered > 0)::int AS answered_any,
         COUNT(pp.person) FILTER (WHERE pp.completed)::int AS completed,
         COALESCE(SUM(pp.answered), 0)::int AS items_scored,
         SUM(pp.acc_sum) / NULLIF(SUM(pp.answered), 0) AS avg_score"""


# --------------------------------------------------------------------------- helpers

KIND_TYPE = {"live": "live", "homework": "homework", "class": "one-screen"}
MODE_KIND = {"all": None, "live": "live", "homework": "homework", "one-screen": "class", "class": "class"}
Mode = Optional[Literal["all", "live", "homework", "one-screen", "class"]]


def _title(kind: str, title: Optional[str]) -> str:
    return title or {"live": "Live quiz", "homework": "Homework quiz"}.get(kind, "")


def _params(program: Optional[str] = None, school: Optional[str] = None, school_key: Optional[str] = None,
            from_: Optional[date] = None, to: Optional[date] = None, kind: Optional[str] = None,
            sid: Optional[UUID] = None, mode: Mode = None) -> dict:
    if mode and kind is None:
        kind = MODE_KIND[mode]
    # `program` is DEPRECATED (the app no longer collects it): still accepted as an exact case-insensitive filter
    # for old links, never reported, no "(not set)" bucket.
    prog = (program or "").strip()
    prog_p = prog.lower() or None
    like = school_key_p = None
    s = (school or "").strip()
    if s:
        if s.lower() == NOT_SET:
            school_key_p = ""
        else:
            like = "%" + re.sub(r"([\\%_])", r"\\\1", s) + "%"
    if school_key is not None:
        k = " ".join(school_key.split()).lower()
        school_key_p = "" if k == NOT_SET else k
    return {"prog": prog_p, "school_like": like, "school_key": school_key_p, "from": from_, "to": to,
            "kind": kind, "sid": sid, "threshold": COMPLETION_THRESHOLD}


@contextmanager
def _ro() -> Iterator[Any]:
    """Pooled connection inside a READ ONLY transaction (reports never write)."""
    with db.connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn


def _f(v: Any, nd: int = 2) -> Optional[float]:
    if v is None:
        return None
    return round(float(v), nd)


def _rate(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def _label(v: str) -> str:
    return v if v else NOT_SET


def _kpis(r: dict) -> dict:
    return {
        "participants": r["participants"] or 0,
        "participated": r["participated"] or 0,
        "participation_rate": _rate(r["participated"] or 0, r["participants"] or 0),
        "joined": r["joined"] or 0,
        "answered_any": r["answered_any"] or 0,
        "completed": r["completed"] or 0,
        "completion_rate": _rate(r["completed"] or 0, r["joined"] or 0),
        "avg_score_pct": _f(r["avg_score"]),
    }


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s or "all")[:60].strip("-") or "all"


def _csv(header: list[str], rows: list[list], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pct(v: Optional[float]) -> str:
    return "" if v is None else f"{v:.2f}"


def _filters_out(program, school, from_, to, mode=None) -> dict:
    return {"school": (school or "").strip() or None,
            "mode": mode if mode and mode != "all" else None,
            "from": from_.isoformat() if from_ else None, "to": to.isoformat() if to else None}


Fmt = Optional[Literal["json", "csv"]]
DEPRECATED_PROGRAM = Query(None, deprecated=True, description="deprecated: the app no longer collects program")
FROM_Q = Query(default=None, alias="from", description="inclusive start date YYYY-MM-DD (session date)")


def _page(limit: int, offset: int, fmt: Fmt) -> tuple[int, int]:
    return (CSV_MAX_ROWS, 0) if fmt == "csv" else (limit, offset)


def _check_dates(from_: Optional[date], to: Optional[date]) -> None:
    if from_ and to and from_ > to:
        raise HTTPException(422, "'from' must be on or before 'to'")


# --------------------------------------------------------------------------- GET /summary

@router.get("/summary")
def summary(program: Optional[str] = DEPRECATED_PROGRAM, school: Optional[str] = None, mode: Mode = None,
            from_: Optional[date] = FROM_Q, to: Optional[date] = None, format: Fmt = None):
    _check_dates(from_, to)
    p = _params(program, school, from_=from_, to=to, mode=mode)
    with _ro() as conn:
        tot = conn.execute(
            f"""WITH {SS}, {PP}
                SELECT (SELECT COUNT(*) FROM ss)::int AS sessions,
                       (SELECT COUNT(*) FROM ss WHERE kind = 'live')::int AS live_games,
                       (SELECT COUNT(*) FROM ss WHERE kind = 'homework')::int AS homework_games,
                       (SELECT COUNT(*) FROM ss WHERE kind = 'class')::int AS class_sessions,
                       (SELECT COUNT(DISTINCT lower(school)) FROM ss WHERE school <> '')::int AS schools,
                       (SELECT COUNT(*) FROM ss WHERE school = '')::int AS sessions_school_not_set,
                       (SELECT MIN(at)::date FROM ss) AS date_from, (SELECT MAX(at)::date FROM ss) AS date_to,
                       {AGG}
                  FROM pp""", p).fetchone()
    kp = _kpis(tot)
    out = {
        "filters": _filters_out(program, school, from_, to, mode),
        "sessions": tot["sessions"], "live_games": tot["live_games"], "homework_games": tot["homework_games"],
        "class_sessions": tot["class_sessions"],
        "schools": tot["schools"], "sessions_school_not_set": tot["sessions_school_not_set"],
        **kp,
        "date_range": {"from": tot["date_from"].isoformat() if tot["date_from"] else None,
                       "to": tot["date_to"].isoformat() if tot["date_to"] else None},
        "funnel": [
            {"step": "joined", "count": kp["joined"], "pct": 1.0 if kp["joined"] else 0.0},
            {"step": "answered", "count": kp["answered_any"], "pct": _rate(kp["answered_any"], kp["joined"])},
            {"step": "completed", "count": kp["completed"], "pct": _rate(kp["completed"], kp["joined"])},
        ],
    }
    if format != "csv":
        return out
    cols = ["scope", "sessions", "live_games", "homework_games", "class_sessions", "schools", "participants",
            "participated", "participation_rate", "joined", "answered_any", "completed", "completion_rate",
            "avg_score_pct", "date_from", "date_to"]
    row = ["all schools" if not (school or "").strip() else f"schools matching: {school.strip()}", out["sessions"],
           out["live_games"], out["homework_games"], out["class_sessions"], out["schools"], out["participants"],
           out["participated"], f"{out['participation_rate']:.4f}", out["joined"], out["answered_any"],
           out["completed"], f"{out['completion_rate']:.4f}", _pct(out["avg_score_pct"]),
           out["date_range"]["from"], out["date_range"]["to"]]
    fname = f"reports-summary-{_slug(school or 'all-schools')}-{_slug(mode or 'all-modes')}-{date.today().isoformat()}.csv"
    return _csv(cols, [row], fname)


# --------------------------------------------------------------------------- GET /schools

SCHOOL_SORTS = {
    "name": "(sa.skey = '') {dir}, sa.skey {dir}",
    "sessions": "sa.sessions {dir}, sa.skey",
    "participants": "COALESCE(pa.participants, 0) {dir}, sa.skey",
    "participated": "COALESCE(pa.participated, 0) {dir}, sa.skey",
    "participation_rate": "COALESCE(pa.participated::numeric / NULLIF(pa.participants, 0), 0) {dir}, sa.skey",
    "completion_rate": "COALESCE(pa.completed::numeric / NULLIF(pa.joined, 0), 0) {dir}, sa.skey",
    "avg_score": "pa.avg_score {dir} NULLS LAST, sa.skey",
    "last_session": "sa.last_at {dir}, sa.skey",
}


@router.get("/schools")
def schools(program: Optional[str] = DEPRECATED_PROGRAM, school: Optional[str] = None, mode: Mode = None,
            from_: Optional[date] = FROM_Q, to: Optional[date] = None,
            sort: Literal["name", "sessions", "participants", "participated", "participation_rate", "completion_rate",
                          "avg_score", "last_session"] = "name",
            dir: Literal["asc", "desc"] = "asc",
            limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000), format: Fmt = None):
    _check_dates(from_, to)
    p = _params(program, school, from_=from_, to=to, mode=mode)
    lim, off = _page(limit, offset, format)
    p |= {"limit": lim, "offset": off}
    order = SCHOOL_SORTS[sort].format(dir="DESC" if dir == "desc" else "ASC")  # whitelisted constants only
    with _ro() as conn:
        rows = conn.execute(
            f"""WITH {SS}, {PP},
                sa AS (SELECT lower(school) AS skey, mode() WITHIN GROUP (ORDER BY school) AS school,
                              COUNT(*)::int AS sessions, COUNT(*) FILTER (WHERE kind = 'live')::int AS live_games,
                              COUNT(*) FILTER (WHERE kind = 'homework')::int AS homework_games,
                              COUNT(*) FILTER (WHERE kind = 'class')::int AS class_sessions, MAX(at) AS last_at
                         FROM ss GROUP BY 1),
                pa AS (SELECT lower(pp.school) AS skey, {AGG} FROM pp GROUP BY 1)
                SELECT sa.*, pa.participants, pa.participated, pa.joined, pa.answered_any, pa.completed,
                       pa.avg_score, COUNT(*) OVER () AS total
                  FROM sa LEFT JOIN pa USING (skey)
                 ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s""", p).fetchall()
    items = [{
        "school": _label(r["school"]), "school_key": _label(r["school"]),
        "sessions": r["sessions"], "live_games": r["live_games"], "homework_games": r["homework_games"],
        "class_sessions": r["class_sessions"],
        **_kpis({k: r[k] or 0 for k in ("participants", "participated", "joined", "answered_any", "completed")}
                | {"avg_score": r["avg_score"]}),
        "last_session_date": r["last_at"].date().isoformat() if r["last_at"] else None,
    } for r in rows]
    total = rows[0]["total"] if rows else 0
    if format == "csv":
        cols = ["school", "sessions", "live_games", "homework_games", "class_sessions", "participants",
                "participated", "participation_rate", "completed", "completion_rate", "avg_score_pct",
                "last_session_date"]
        data = [[i["school"], i["sessions"], i["live_games"], i["homework_games"], i["class_sessions"], i["participants"],
                 i["participated"], f"{i['participation_rate']:.4f}", i["completed"], f"{i['completion_rate']:.4f}",
                 _pct(i["avg_score_pct"]), i["last_session_date"]] for i in items]
        return _csv(cols, data, f"reports-schools-{_slug(school or 'all-schools')}-{date.today().isoformat()}.csv")
    return {"filters": _filters_out(program, school, from_, to, mode), "items": items, "total": total,
            "limit": limit, "offset": offset, "sort": sort, "dir": dir}


# --------------------------------------------------------------------------- GET /schools/{school}/sessions

def _csv_url(kind: str, sid: Any) -> Optional[str]:
    # The existing per-game CSV: class sessions have a public one; the live one needs the teacher's host token,
    # which reports never have → null (use report_csv_url instead).
    return f"/api/class/sessions/{sid}/participation.csv" if kind == "class" else None


@router.get("/schools/{school}/sessions")
def school_sessions(school: str, program: Optional[str] = DEPRECATED_PROGRAM, mode: Mode = None,
                    from_: Optional[date] = FROM_Q, to: Optional[date] = None,
                    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
                    format: Fmt = None):
    _check_dates(from_, to)
    if len(school) > 300:
        raise HTTPException(422, "school too long")
    p = _params(program, school_key=school, from_=from_, to=to, mode=mode)
    lim, off = _page(limit, offset, format)
    p |= {"limit": lim, "offset": off}
    with _ro() as conn:
        rows = conn.execute(
            f"""WITH {SS}, {PP}
                SELECT s.kind, s.id, s.title, s.teacher_name, s.school, s.at, s.status, s.played, s.grouping,
                       {AGG}, COUNT(*) OVER () AS total
                  FROM ss s LEFT JOIN pp ON pp.sid = s.id AND pp.kind = s.kind
                 GROUP BY s.kind, s.id, s.title, s.teacher_name, s.school, s.at, s.status, s.played, s.grouping
                 ORDER BY s.at DESC, s.id LIMIT %(limit)s OFFSET %(offset)s""", p).fetchall()
    items = [{
        "kind": r["kind"], "type": KIND_TYPE[r["kind"]],
        "id": str(r["id"]), "title": _title(r["kind"], r["title"]),
        "date": r["at"].date().isoformat(), "started_at": r["at"].isoformat(),
        "teacher": r["teacher_name"] or "", "school": _label(r["school"]), "status": r["status"],
        "grouping": r["grouping"], "questions": r["played"],
        **_kpis(r),
        "csv_url": _csv_url(r["kind"], r["id"]),
        "report_csv_url": f"/api/reports/sessions/{r['kind']}/{r['id']}?format=csv",
    } for r in rows]
    total = rows[0]["total"] if rows else 0
    label = _label(" ".join(school.split()))
    if format == "csv":
        cols = ["school", "type", "title", "date", "teacher", "status", "participants", "participated",
                "participation_rate", "completed", "completion_rate", "avg_score_pct", "session_id"]
        data = [[label, i["type"], i["title"], i["date"], i["teacher"], i["status"], i["participants"],
                 i["participated"], f"{i['participation_rate']:.4f}", i["completed"], f"{i['completion_rate']:.4f}",
                 _pct(i["avg_score_pct"]), i["id"]] for i in items]
        return _csv(cols, data, f"reports-sessions-{_slug(label)}-{date.today().isoformat()}.csv")
    return {"school": label, "filters": _filters_out(program, None, from_, to, mode), "items": items,
            "total": total, "limit": limit, "offset": offset}


# --------------------------------------------------------------------------- GET /sessions/{kind}/{id}

@router.get("/sessions/{kind}/{session_id}")
def session_students(kind: Literal["live", "homework", "class"], session_id: UUID,
                     limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0, le=100000),
                     format: Fmt = None):
    p = _params(kind=kind, sid=session_id)
    lim, off = _page(limit, offset, format)
    with _ro() as conn:
        meta = conn.execute(f"WITH {SS} SELECT * FROM ss", p).fetchone()
        if not meta:
            raise HTTPException(404, "Session not found")
        rows = conn.execute(f"WITH {SS}, {PP} SELECT * FROM pp ORDER BY score DESC, lower(name), person_id",
                            p).fetchall()
        absent = []
        if kind == "class":
            absent = conn.execute(
                """SELECT st.id, st.name FROM attendance a JOIN student st ON st.id = a.student_id
                    WHERE a.class_session_id = %s AND NOT a.present ORDER BY lower(st.name), st.id""",
                (session_id,)).fetchall()
    scores = [r["score"] for r in rows]
    students = []
    for r in rows:
        acc = float(r["acc_sum"]) / r["answered"] if r["answered"] else None
        students.append({
            "id": r["person_id"], "name": r["name"], "present": True, "answered": r["answered"],
            "correct": r["correct"], "accuracy_pct": _f(acc), "score": r["score"],
            "rank": 1 + sum(1 for x in scores if x > r["score"]), "completed": bool(r["completed"]),
            **({"present_for": r["present_for"]} if kind == "live" else {}),
            **({"progress": min(r["current_idx"] or 0, meta["played"]), "total": meta["played"],  # LEAST(current_idx, questions)
                "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None}
               if kind == "homework" else {}),
        })
    for a in absent:
        students.append({"id": a["id"], "name": a["name"], "present": False, "answered": 0, "correct": 0,
                         "accuracy_pct": None, "score": 0, "rank": None, "completed": False})
    agg = {"participants": len(rows), "participated": sum(1 for r in rows if r["answered"]),
           "joined": len(rows), "answered_any": sum(1 for r in rows if r["answered"]),
           "completed": sum(1 for r in rows if r["completed"])}
    n_items = sum(r["answered"] for r in rows)
    agg["avg_score"] = (sum(float(r["acc_sum"]) for r in rows) / n_items) if n_items else None
    info = {
        "kind": kind, "type": KIND_TYPE[kind], "id": str(meta["id"]),
        "title": _title(kind, meta["title"]), "date": meta["at"].date().isoformat(),
        "started_at": meta["at"].isoformat(), "teacher": meta["teacher_name"] or "",
        "school": _label(meta["school"]), "status": meta["status"], "grouping": meta["grouping"],
        "questions": meta["played"], **_kpis(agg), "csv_url": _csv_url(kind, meta["id"]),
    }
    total = len(students)
    page = students[off:off + lim]
    if format == "csv":
        cols = ["school", "type", "title", "date", "teacher", "name", "present", "answered", "correct",
                "accuracy_pct", "score", "rank", "completed"]
        if kind == "homework":
            cols += ["progress", "finished_at"]
        data = [[info["school"], info["type"], info["title"], info["date"], info["teacher"],
                 s["name"], "yes" if s["present"] else "no", s["answered"], s["correct"], _pct(s["accuracy_pct"]),
                 s["score"], s["rank"], "yes" if s["completed"] else "no"]
                + ([f"{s['progress']}/{s['total']}", s["finished_at"]] if kind == "homework" else [])
                for s in page]
        fname = f"reports-students-{_slug(info['school'])}-{info['date']}-{kind}-{str(meta['id'])[:8]}.csv"
        return _csv(cols, data, fname)
    return {"session": info, "students": page, "total": total, "limit": limit, "offset": offset}


# --------------------------------------------------------------------------- GET /students?school=

NAME_KEY = r"lower(regexp_replace(btrim(pp.name), '\s+', ' ', 'g'))"


@router.get("/students")
def students_progress(school: str = Query(..., min_length=1, max_length=300), program: Optional[str] = DEPRECATED_PROGRAM,
                      mode: Mode = None,
                      from_: Optional[date] = FROM_Q, to: Optional[date] = None,
                      limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
                      format: Fmt = None):
    _check_dates(from_, to)
    p = _params(program, school_key=school, from_=from_, to=to, mode=mode)
    lim, off = _page(limit, offset, format)
    p |= {"limit": lim, "offset": off}
    with _ro() as conn:
        rows = conn.execute(
            f"""WITH {SS}, {PP},
                x AS (SELECT pp.*, {NAME_KEY} AS nkey FROM pp),
                keys AS (SELECT nkey, COUNT(*) OVER () AS total FROM x GROUP BY nkey
                          ORDER BY nkey LIMIT %(limit)s OFFSET %(offset)s)
                SELECT x.kind, x.sid, x.title, x.at, x.name, x.answered, x.acc_sum, x.score, x.nkey, keys.total
                  FROM x JOIN keys USING (nkey)
                 ORDER BY x.nkey, x.at, x.sid""", p).fetchall()
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["nkey"], []).append(r)
    items = []
    for nkey, rs in groups.items():
        sessions = []
        for r in rs:
            sc = float(r["acc_sum"]) / r["answered"] if r["answered"] else None
            sessions.append({"kind": r["kind"], "session_id": str(r["sid"]), "date": r["at"].date().isoformat(),
                             "type": KIND_TYPE[r["kind"]], "title": _title(r["kind"], r["title"]),
                             "name_as_entered": r["name"], "answered": r["answered"], "score_pct": _f(sc),
                             "points": r["score"]})
        scored = [s["score_pct"] for s in sessions if s["score_pct"] is not None]
        first = scored[0] if scored else None
        last = scored[-1] if scored else None
        items.append({"name": " ".join(rs[-1]["name"].split()), "match_key": nkey,
                      "sessions_attended": len(sessions), "sessions_scored": len(scored),
                      "first_score_pct": first, "last_score_pct": last,
                      "improvement_pct": round(last - first, 2) if len(scored) >= 2 else None,
                      "sessions": sessions})
    total = rows[0]["total"] if rows else 0
    label = _label(" ".join(school.split()))
    if format == "csv":
        cols = ["school", "name (matched by name, approximate)", "sessions_attended", "sessions_scored",
                "first_score_pct", "last_score_pct", "improvement_pct", "score_pct_by_session (date order)"]
        data = [[label, i["name"], i["sessions_attended"], i["sessions_scored"], _pct(i["first_score_pct"]),
                 _pct(i["last_score_pct"]), _pct(i["improvement_pct"]),
                 " | ".join(f"{s['date']} {s['type']}: {_pct(s['score_pct']) or '-'}" for s in i["sessions"])]
                for i in items]
        return _csv(cols, data, f"reports-progress-{_slug(label)}-{date.today().isoformat()}.csv")
    return {"school": label, "matching": "name, approximate", "note": MATCH_NOTE,
            "filters": _filters_out(program, None, from_, to, mode), "items": items, "total": total,
            "limit": limit, "offset": offset}
