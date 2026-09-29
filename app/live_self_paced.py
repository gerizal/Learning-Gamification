"""Self-paced / homework mode for live games (live_game.mode = 'self_paced'). See CONTRACT.md
"SELF-PACED / HOMEWORK MODE" + "Self-paced — implementation notes".

Same tables as the live game (db/012_self_paced.sql). Each player walks through the question list on their own:
`POST /games/{pin}/me/start` starts the clock of their current question (server clock, idempotent), the answer must
carry `idx == current_idx`, is scored at once (instant feedback, `applied = true`) and advances the player.
Everything is server-authoritative and lazy:
  * a started question whose `time_limit + 3 s` passed is recorded as "no answer" (no row, 0 pts, streak unchanged)
    and the player advances — on that player's next state read / start / answer;
  * a game past `closes_at` is ended on the first read after the deadline (status ended, ended_at = closes_at).
Locking: every progress mutation holds `FOR UPDATE` on the live_player row; host changes hold `FOR UPDATE` on
live_game (see live._host_action); answers also take `FOR SHARE` on live_game so pause / end serialise with them.

This module is imported at the bottom of app/live.py (it registers its routes on live.router).
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from fastapi import Header, HTTPException
from psycopg.types.json import Jsonb

from . import db, scoring
from . import live as L

SELF_PACED = "self_paced"
MAX_DEADLINE_DAYS = 30
_rng = random.SystemRandom()


def is_sp(g: Optional[dict]) -> bool:
    return bool(g) and g.get("mode") == SELF_PACED


class Err(Exception):
    """An error decided inside a transaction that must still COMMIT (e.g. a lazy expiry happened first)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail

    def http(self) -> HTTPException:
        return HTTPException(self.status, self.detail)


# --------------------------------------------------------------------------- deadline / auto-close

def check_deadline(conn, closes_at: datetime, *, must_be_future: bool) -> bool:
    """422 if closes_at is more than 30 days away (or not in the future when required). Returns: is it past?
    DB clock only."""
    r = conn.execute(
        """SELECT %s::timestamptz <= clock_timestamp() AS past,
                  %s::timestamptz > clock_timestamp() + make_interval(days => %s) AS too_far""",
        (closes_at, closes_at, MAX_DEADLINE_DAYS)).fetchone()
    if r["too_far"]:
        raise HTTPException(422, f"closes_at: at most {MAX_DEADLINE_DAYS} days from now")
    if must_be_future and r["past"]:
        raise HTTPException(422, "closes_at: must be in the future")
    return bool(r["past"])


def autoclose(conn, g: dict) -> dict:
    """Lazy auto-close: an open self-paced game past closes_at becomes ended (ended_at = closes_at), once.
    The conditional UPDATE is atomic (a concurrent second caller re-checks the WHERE and matches nothing)."""
    if not is_sp(g) or g["status"] != "open" or g.get("closes_at") is None:
        return g
    r = conn.execute(
        """UPDATE live_game SET status = 'ended', ended_at = closes_at, phase_started_at = clock_timestamp()
            WHERE id = %s AND mode = 'self_paced' AND status = 'open'
              AND closes_at IS NOT NULL AND closes_at <= clock_timestamp()
        RETURNING *""", (g["id"],)).fetchone()
    if r is None:
        return g
    L.notify(conn, g["id"])
    return r


# --------------------------------------------------------------------------- per-player progress

def _total(conn, game_id: Any) -> int:
    return conn.execute("SELECT COUNT(*)::int AS n FROM live_question WHERE game_id = %s",
                        (game_id,)).fetchone()["n"]


def real_idx(p: dict, pos: int) -> int:
    """live_question.idx served at the player's position `pos` (per-player order when shuffled)."""
    order = p.get("question_order")
    return order[pos] if order else pos


def _lock_player(conn, pid: int) -> dict:
    return conn.execute("SELECT * FROM live_player WHERE id = %s FOR UPDATE", (pid,)).fetchone()


def expire(conn, g: dict, pid: int, total: int) -> bool:
    """Caller holds the live_player row lock. A started question past time_limit + 3 s is recorded as no answer
    (no live_answer row, 0 points, streak unchanged) and the player advances; finishing the last question sets
    finished_at to the moment it expired. Unstarted questions never expire."""
    r = conn.execute(
        """UPDATE live_player p
              SET current_idx = p.current_idx + 1, question_started_at = NULL,
                  finished_at = CASE WHEN p.current_idx + 1 >= %(total)s
                                     THEN p.question_started_at + make_interval(secs => q.time_limit_sec + %(grace)s)
                                END
             FROM live_question lq JOIN question q ON q.id = lq.question_id
            WHERE p.id = %(pid)s AND lq.game_id = p.game_id
              AND lq.idx = COALESCE(p.question_order[p.current_idx + 1], p.current_idx)
              AND p.question_started_at IS NOT NULL AND p.finished_at IS NULL
              AND clock_timestamp() > p.question_started_at + make_interval(secs => q.time_limit_sec + %(grace)s)
        RETURNING p.id""",
        {"pid": pid, "total": total, "grace": scoring.LIVE_GRACE_SEC}).fetchone()
    if r is None:
        return False
    L.notify(conn, g["id"])
    return True


def touch_player(conn, g: dict, pid: int) -> dict:
    """On a player's own state read: auto-close the game, expire their timed-out question. Returns the game row."""
    g = autoclose(conn, g)
    if g["status"] != "open":
        return g
    p = conn.execute("""SELECT p.question_started_at, p.finished_at FROM live_player p WHERE p.id = %s""",
                     (pid,)).fetchone()
    if p["question_started_at"] is not None and p["finished_at"] is None:
        _lock_player(conn, pid)
        expire(conn, g, pid, _total(conn, g["id"]))
    return g


def _check_playable(g: dict) -> None:
    if g["status"] != "open":
        raise Err(409, "This game has ended")
    if g["paused"]:
        raise Err(409, "Game is paused by the teacher")


def _start(pin: str, token: Optional[str]) -> dict:
    """Start (or resume) the clock of the player's current question. Idempotent: never resets a running clock."""
    err = None
    with db.connection() as conn:
        g, p = L._player(conn, pin, token)
        if not is_sp(g):
            raise HTTPException(409, "Not a self-paced game")
        try:
            g = autoclose(conn, g)
            if g["status"] == "open":
                p = _lock_player(conn, p["id"])
                if p["is_kicked"]:
                    raise Err(403, "You were removed from this game")
                total = _total(conn, g["id"])
                if expire(conn, g, p["id"], total):  # timed out while away: advance first, then start the next
                    p = _lock_player(conn, p["id"])
            _check_playable(g)
            if p["finished_at"] is not None or p["current_idx"] >= total:
                raise Err(409, "You have finished this game")
            if p["question_started_at"] is None:
                conn.execute("UPDATE live_player SET question_started_at = clock_timestamp() WHERE id = %s",
                             (p["id"],))
                L.notify(conn, g["id"])
            state = L.build_state(conn, g, "player", p["id"])
        except Err as e:
            err = e  # commit what happened (auto-close / expiry), then answer the error
    if err is not None:
        raise err.http()
    return state


@L.router.post("/games/{pin}/me/start")
def start_my_question(pin: str, x_player_token: Optional[str] = Header(default=None)):
    """Self-paced: start the clock of my current question; returns my player state (with `question`)."""
    return _start(pin, x_player_token)


# --------------------------------------------------------------------------- answer

Q_COLS = """q.game_mode, q.target_text, q.keywords, q.options, q.correct_option, q.difficulty, q.base_points,
            q.time_limit_sec, q.prompt, q.image_url, q.image_alt, lq.idx"""


def answer_precheck(conn, g: dict, p: dict, client_idx: Optional[int]) -> dict:
    """Auth already done (404/403). Returns ctx, or {'error': Err} to raise AFTER commit (a lazy expiry
    recorded here must survive the 409). answer_ms = DB clock at receipt − question_started_at."""
    try:
        if client_idx is None:
            raise Err(422, "idx: required for a self-paced game (your current question position)")
        g = autoclose(conn, g)
        _check_playable(g)
        p = _lock_player(conn, p["id"])
        if p["is_kicked"]:
            raise Err(403, "You were removed from this game")
        total = _total(conn, g["id"])
        before = p["current_idx"]
        if expire(conn, g, p["id"], total):
            p = _lock_player(conn, p["id"])
            if client_idx == before:
                raise Err(409, "Time is up")
        if p["finished_at"] is not None or p["current_idx"] >= total:
            raise Err(409, "You have finished this game")
        pos = p["current_idx"]
        if client_idx != pos:
            raise Err(409, f"Question {client_idx} is not your current question (current is {pos})")
        if p["question_started_at"] is None:
            raise Err(409, "Question not started (call /me/start first)")
        idx = real_idx(p, pos)
        q = conn.execute(f"""SELECT {Q_COLS} FROM live_question lq JOIN question q ON q.id = lq.question_id
                              WHERE lq.game_id = %s AND lq.idx = %s""", (g["id"], idx)).fetchone()
        elapsed = conn.execute(
            "SELECT (EXTRACT(EPOCH FROM clock_timestamp() - %s::timestamptz) * 1000)::int AS ms",
            (p["question_started_at"],)).fetchone()["ms"]
        if elapsed > q["time_limit_sec"] * 1000 + L.GRACE_MS:
            raise Err(409, "Time is up")
        if conn.execute("SELECT 1 FROM live_answer WHERE game_id = %s AND idx = %s AND player_id = %s",
                        (g["id"], idx, p["id"])).fetchone():
            raise Err(409, "Already answered")
    except Err as e:
        return {"error": e}
    return {"mode": SELF_PACED, "game_id": g["id"], "idx": idx, "pos": pos, "player_id": p["id"],
            "started": p["question_started_at"], "answer_ms": max(0, elapsed), "q": q, "total": total}


def record_answer(ctx: dict, result: dict, choice: Optional[int]) -> dict:
    """Score + store + advance in ONE transaction under FOR SHARE live_game + FOR UPDATE live_player.
    The answer is applied at once (applied = true) — exactly once: the row insert (UNIQUE) and the score update
    happen together, and a second request for the same position finds current_idx already moved (409)."""
    q = ctx["q"]
    with db.connection() as conn:
        g = conn.execute("SELECT * FROM live_game WHERE id = %s FOR SHARE", (ctx["game_id"],)).fetchone()
        if g["status"] != "open":
            raise HTTPException(409, "This game has ended")
        if g["paused"]:
            raise HTTPException(409, "Game is paused by the teacher")
        p = _lock_player(conn, ctx["player_id"])
        if p["is_kicked"]:
            raise HTTPException(403, "You were removed from this game")
        if (p["current_idx"] != ctx["pos"] or p["finished_at"] is not None
                or p["question_started_at"] != ctx["started"]):
            raise HTTPException(409, "Already answered")
        streak = scoring.next_streak(p["streak"], result["passed"])
        # speed_bonus off (homework default): speed factor 1.0 whatever the answer time
        pts = scoring.live_points(base_points=q["base_points"], difficulty=q["difficulty"],
                                  accuracy=result["accuracy"], passed=result["passed"],
                                  answer_ms=ctx["answer_ms"] if g["speed_bonus"] else 0,
                                  time_limit_sec=q["time_limit_sec"], streak=streak)
        fb = {**result["feedback"], "streak": streak, "speed_factor": pts["speed_factor"],
              "streak_multiplier": pts["streak_multiplier"]}
        try:
            with conn.transaction():
                a = conn.execute(
                    """INSERT INTO live_answer (game_id, idx, player_id, transcript, choice, accuracy, passed,
                                                stars, points, answer_ms, feedback, applied)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true) RETURNING *""",
                    (ctx["game_id"], ctx["idx"], p["id"], "", choice, result["accuracy"],
                     result["passed"], result["stars"], pts["points"], ctx["answer_ms"], Jsonb(fb))).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "Already answered")
        nxt = conn.execute(
            """UPDATE live_player SET score = score + %s, streak = %s, current_idx = current_idx + 1,
                      question_started_at = NULL,
                      finished_at = CASE WHEN current_idx + 1 >= %s THEN clock_timestamp() END
                WHERE id = %s RETURNING current_idx, finished_at""",
            (pts["points"], streak, ctx["total"], p["id"])).fetchone()
        L.notify(conn, ctx["game_id"])
    ctx["after"] = {"current_idx": nxt["current_idx"], "total": ctx["total"],
                    "finished": nxt["finished_at"] is not None}
    return {**L._answer_result(a), "correct": L._correct_view(q)}


# --------------------------------------------------------------------------- join / host settings

def join_checks(conn, g: dict) -> dict:
    """Inside live._join (game row locked FOR UPDATE). Returns the game row (auto-closed if due)."""
    g = autoclose(conn, g)
    if g["status"] == "ended":
        raise HTTPException(409, "This game has ended")
    if g["paused"]:
        raise HTTPException(409, "Game is paused by the teacher")
    return g


def question_order_for(conn, g: dict) -> Optional[list[int]]:
    if not g["shuffle_per_player"]:
        return None
    order = list(range(_total(conn, g["id"])))
    _rng.shuffle(order)
    return order


def update_settings(conn, g: dict, body) -> Optional[bool]:
    """PATCH /settings for a self-paced game (game row locked, already auto-closed). False = no change."""
    sent = body.model_fields_set
    if "instant_feedback" in sent and body.instant_feedback is False:
        raise HTTPException(422, "instant_feedback: always on in a self-paced game")
    changes: dict[str, Any] = {}
    if body.allow_rename is not None and body.allow_rename != g["allow_rename"]:
        changes["allow_rename"] = body.allow_rename
    if "paused" in sent:
        if body.paused is None:
            raise HTTPException(422, "paused: must be true or false")
        if body.paused != g["paused"]:
            changes["paused"] = body.paused
    past = False
    if "closes_at" in sent:
        if body.closes_at is not None:
            past = check_deadline(conn, body.closes_at, must_be_future=False)
        if body.closes_at != g["closes_at"]:
            changes["closes_at"] = body.closes_at
    if g["status"] == "ended" and ({"paused", "closes_at"} & set(changes)):
        raise HTTPException(409, "This game has ended")
    if not changes:
        return False
    conn.execute(
        "UPDATE live_game SET allow_rename = %s, paused = %s, closes_at = %s WHERE id = %s",
        (changes.get("allow_rename", g["allow_rename"]), changes.get("paused", g["paused"]),
         changes.get("closes_at", g["closes_at"]), g["id"]))
    if "closes_at" in changes and past:
        # shortened into the past -> closed now (ended_at = now: answers until this moment were legitimate)
        conn.execute("UPDATE live_game SET status = 'ended', ended_at = clock_timestamp(), "
                     "phase_started_at = clock_timestamp() WHERE id = %s AND status = 'open'", (g["id"],))
    return None


# --------------------------------------------------------------------------- snapshot + state

QUESTIONS_SQL = f"""
SELECT {Q_COLS},
       COUNT(a.id) FILTER (WHERE p.id IS NOT NULL)::int AS answered,
       COUNT(a.id) FILTER (WHERE p.id IS NOT NULL AND a.passed)::int AS correct
  FROM live_question lq JOIN question q ON q.id = lq.question_id
  LEFT JOIN live_answer a ON a.game_id = lq.game_id AND a.idx = lq.idx
  LEFT JOIN live_player p ON p.id = a.player_id AND NOT p.is_kicked
 WHERE lq.game_id = %s
 GROUP BY lq.game_id, lq.idx, q.id
 ORDER BY lq.idx"""

# One ordered query: players with progress, rank and their most recent answer (index live_answer_player_idx).
PLAYERS_SQL = """
SELECT p.id, p.nickname, p.score, p.streak, p.joined_at, p.current_idx, p.question_started_at, p.finished_at,
       p.question_order, RANK() OVER (ORDER BY p.score DESC)::int AS rank,
       la.id AS a_id, la.idx AS a_idx, la.transcript AS a_transcript, la.choice AS a_choice,
       la.accuracy AS a_accuracy, la.passed AS a_passed, la.stars AS a_stars, la.points AS a_points,
       la.answer_ms AS a_answer_ms, la.feedback AS a_feedback, la.created_at AS a_created_at
  FROM live_player p
  LEFT JOIN LATERAL (SELECT * FROM live_answer a WHERE a.player_id = p.id ORDER BY a.id DESC LIMIT 1) la ON true
 WHERE p.game_id = %s AND NOT p.is_kicked
 ORDER BY p.score DESC, lower(p.nickname), p.id"""


def fetch_snapshot(conn, g: dict) -> dict:
    """Self-paced snapshot: 3 queries (+2 when the deadline just passed), independent of the player count."""
    if g["status"] == "open" and g["closes_at"] is not None and g["closes_at"] <= g["now"]:
        autoclose(conn, g)
        g = conn.execute("SELECT *, clock_timestamp() AS now FROM live_game WHERE id = %s", (g["id"],)).fetchone()
    qs = conn.execute(QUESTIONS_SQL, (g["id"],)).fetchall()
    rows = conn.execute(PLAYERS_SQL, (g["id"],)).fetchall()
    return {"sp": True, "g": g, "total": len(qs), "qs": qs, "rows": rows}


def _last_answer(r: dict) -> Optional[dict]:
    if r["a_id"] is None:
        return None
    return {k: r["a_" + k] for k in ("idx", "transcript", "choice", "accuracy", "passed", "stars", "points",
                                     "answer_ms", "feedback", "created_at")}


def _last_active(r: dict) -> datetime:
    return max(t for t in (r["joined_at"], r["question_started_at"], r["a_created_at"], r["finished_at"])
               if t is not None)


def render_state(snap: dict, role: str, me_id: Optional[int] = None) -> Optional[dict]:
    """Self-paced LiveState (pure). Never contains a correct answer except the player's OWN last answered one."""
    g, qs, rows, total = snap["g"], snap["qs"], snap["rows"], snap["total"]
    qmap = {q["idx"]: q for q in qs}
    entries = [{"rank": r["rank"], "player_id": r["id"], "nickname": r["nickname"], "score": r["score"],
                "delta_rank": 0} for r in rows]
    answered_total = sum(q["answered"] for q in qs)
    state: dict[str, Any] = {
        "game_id": str(g["id"]), "pin": g["pin"], "status": g["status"], "title": g["title"],
        "mode": SELF_PACED, "closes_at": g["closes_at"], "paused": g["paused"],
        "index": -1, "total": total, "phase_started_at": None, "server_now": g["now"], "time_left_ms": None,
        "settings": {"allow_rename": g["allow_rename"], "instant_feedback": True,
                     "speed_bonus": g["speed_bonus"], "shuffle_per_player": g["shuffle_per_player"]},
        "question": None, "players_count": len(rows), "answered_count": answered_total, "reveal": None,
    }
    if role == "host":
        finished = sum(1 for r in rows if r["finished_at"] is not None)
        in_progress = sum(1 for r in rows if r["finished_at"] is None
                          and (r["current_idx"] > 0 or r["question_started_at"] is not None))
        state["progress"] = {"joined": len(rows), "in_progress": in_progress, "finished": finished}
        state["players"] = [{"id": r["id"], "nickname": r["nickname"], "score": r["score"],
                             "current_idx": min(r["current_idx"], total), "total": total,
                             "finished_at": r["finished_at"], "last_active_at": _last_active(r)}
                            for r in sorted(rows, key=lambda r: (r["joined_at"], r["id"]))]
        state["per_question"] = [{"idx": q["idx"], "prompt": q["prompt"], "answered": q["answered"],
                                  "correct_pct": round(100 * q["correct"] / q["answered"], 1)
                                  if q["answered"] else None} for q in qs]
        state["leaderboard"] = {"top": entries[:L.TOP_N], "rank_changes": []}
        state["summary"] = {"joined": len(rows),
                            "answered_any": sum(1 for r in rows if r["a_id"] is not None)}
        return state

    pos = next((i for i, r in enumerate(rows) if r["id"] == me_id), None)
    if pos is None:
        return None
    me = rows[pos]
    cur = min(me["current_idx"], total)
    started = (me["question_started_at"] is not None and me["finished_at"] is None and cur < total
               and g["status"] == "open")
    if started:
        q = qmap[real_idx(me, cur)]
        state["question"] = {**L._question_view(q), "idx": cur}
        elapsed = (g["now"] - me["question_started_at"]).total_seconds() * 1000
        state["time_left_ms"] = max(0, int(q["time_limit_sec"] * 1000 - elapsed))
        state["phase_started_at"] = me["question_started_at"]
    state["index"] = cur
    last = None
    la = _last_answer(me)
    if la is not None and cur > 0 and la["idx"] == real_idx(me, cur - 1):
        # the player's OWN previous answer (already scored) — the only correct answer a player ever sees
        last = {**L._answer_result(la), "correct": L._correct_view(qmap[la["idx"]])}
    above = rows[pos - 1] if pos > 0 else None
    state["me"] = {"id": me["id"], "nickname": me["nickname"], "score": me["score"], "rank": me["rank"],
                   "streak": me["streak"], "current_idx": cur, "total": total, "finished_at": me["finished_at"],
                   "question_started_at": me["question_started_at"] if started else None,
                   "answered_current": False, "last_result": last}
    state["leaderboard"] = {
        "top": [{k: e[k] for k in ("rank", "nickname", "score", "delta_rank")} for e in entries[:L.TOP_N]],
        "me": {"rank": me["rank"], "score": me["score"],
               "above": None if above is None else {"nickname": above["nickname"],
                                                    "score_gap": above["score"] - me["score"]}},
    }
    return state


def deadline_passed(state: Optional[dict]) -> bool:
    """SSE helper: an open self-paced game whose deadline passed needs a fresh read (which auto-closes it)."""
    if not state or state.get("mode") != SELF_PACED or state.get("status") != "open" or not state.get("closes_at"):
        return False
    ca = state["closes_at"]
    return datetime.now(timezone.utc) >= ca
