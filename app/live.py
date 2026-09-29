"""Live game (Kahoot-style) — routes under /api/live. See CONTRACT.md "LIVE GAME" + "Live — implementation notes".

Teacher (host) creates a game and gets a 6-digit PIN; students join on their own device and answer the
current question (multiple_choice only: tap an option; speaking questions are not supported). The host alone
drives the phases: lobby → question → reveal → leaderboard → question … → ended.

Realtime: every state-changing transaction ends with `pg_notify('live_<game uuid hex>', '{"game_id", "v"}')`
(NOTIFY is transactional, so it fires only on commit). One listener task per process/event loop holds a single
async psycopg connection, LISTENs on the channels that have open SSE streams, and fans notifications out to
per-stream asyncio queues. Each stream then re-reads ITS role's state from the DB — no secret ever travels
through NOTIFY, and any number of uvicorn workers / instances stay consistent.

Integrity: host transitions take `SELECT … FOR UPDATE` on live_game; answers take `FOR SHARE` on live_game
(answers run in parallel, but never interleave with a transition) plus `FOR UPDATE` on the player row, and
UNIQUE(game_id, idx, player_id) is the last line of defence (→ 409). Tokens are compared with
`secrets.compare_digest`.
"""
from __future__ import annotations

import asyncio
import collections
import csv
import io
import json
import logging
import os
import re
import secrets
import threading
import time
import weakref
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import UploadFile as StarletteUploadFile

from . import db, scoring

log = logging.getLogger("playclass.live")

router = APIRouter(prefix="/api/live", tags=["live"])

MC = scoring.MULTIPLE_CHOICE
DEFAULT_MODES = [MC]
SPEAKING_UNSUPPORTED = "speaking questions are not supported"  # 422 detail (owner, 2026-09-28: quiz-only MVP)
GRACE_MS = scoring.LIVE_GRACE_SEC * 1000
HEARTBEAT_SEC = float(os.environ.get("LIVE_HEARTBEAT_SEC", "15"))
NEXT_DEBOUNCE_MS = 700      # /next without {status, index}: a 2nd call within this window → 409
PUSH_MIN_INTERVAL = 0.2     # SSE: at most 5 state pushes / s per stream (bursts are coalesced)
RENAME_COOLDOWN_SEC = 10    # player self-rename: 1 per 10 s (DB clock, live_player.renamed_at)
TOP_N = 10                  # leaderboard.top size
NICK_MAX = 20
PIN_RE = re.compile(r"^\d{6}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SPACE_RE = re.compile(r"\s+")

# SQL filter: only multiple_choice is playable, and only with 2-4 options and a valid correct_option.
PLAYABLE_SQL = ("(q.game_mode = 'multiple_choice' AND cardinality(q.options) BETWEEN 2 AND 4 "
                "AND q.correct_option IS NOT NULL AND q.correct_option < cardinality(q.options))")
# "All packs" (pack_id null) never includes a teacher's private quiz: those are only played when picked by id.
NOT_PRIVATE_SQL = ("(q.pack_id IS NULL OR NOT EXISTS (SELECT 1 FROM question_pack qp "
                   "WHERE qp.id = q.pack_id AND qp.edit_key_hash IS NOT NULL))")


# --------------------------------------------------------------------------- rate limit (in-memory)

class RateLimiter:
    """Sliding window per key. PROTOTYPE ONLY: per process — move to Redis (INCR + EXPIRE) when scaling out."""

    def __init__(self, limit: int, window_sec: float):
        self.limit, self.window = limit, window_sec
        self._hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > self.window:
                dq.popleft()
            if len(dq) >= self.limit:
                return False
            dq.append(now)
            if len(self._hits) > 10000:  # crude memory bound
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    del self._hits[k]
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


join_limiter = RateLimiter(int(os.environ.get("LIVE_JOIN_LIMIT", "10")),
                           float(os.environ.get("LIVE_JOIN_WINDOW_SEC", "10")))
lookup_limiter = RateLimiter(int(os.environ.get("LIVE_LOOKUP_LIMIT", "30")),
                             float(os.environ.get("LIVE_JOIN_WINDOW_SEC", "10")))


def _client_ip(request: Request) -> str:
    # X-Forwarded-For is NOT trusted (spoofable); behind a proxy configure uvicorn --proxy-headers.
    return request.client.host if request.client else "unknown"


# --------------------------------------------------------------------------- LISTEN/NOTIFY broker

def channel_for(game_id: Any) -> str:
    return "live_" + UUID(str(game_id)).hex


def notify(conn, game_id: Any) -> None:
    """Queue a NOTIFY in the current transaction (delivered on commit only). Payload has no secrets."""
    conn.execute(
        "SELECT pg_notify(%s, json_build_object('game_id', %s::text, 'v', pg_current_xact_id()::text)::text)",
        (channel_for(game_id), str(game_id)),
    )


class Broker:
    """One LISTEN connection per event loop; fans NOTIFY payloads out to asyncio queues."""

    POLL_SEC = 0.2  # max delay before a new LISTEN/UNLISTEN is issued

    def __init__(self) -> None:
        self.subs: dict[str, set[asyncio.Queue]] = {}
        self.listening: set[str] = set()
        self.cmds: collections.deque = collections.deque()
        self.connected = asyncio.Event()
        self.task: asyncio.Task | None = None
        # Per-game snapshot cache: every stream of a game in this process shares ONE DB read per change.
        # gen[ch] is bumped on every NOTIFY received; a cached snapshot taken at gen >= wanted is fresh enough
        # (NOTIFY arrives after commit, so a read started after it sees that commit).
        self.gen: dict[str, int] = {}
        self.cache: dict[str, tuple[int, Any]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.fetches = 0  # DB snapshot reads (observability / tests)

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.get_running_loop().create_task(self._run(), name="live-broker")

    async def subscribe(self, channel: str) -> asyncio.Queue:
        self.start()
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.subs.setdefault(channel, set()).add(q)
        if channel not in self.listening:
            fut = asyncio.get_running_loop().create_future()
            self.cmds.append(("LISTEN", channel, fut))
            try:
                await asyncio.wait_for(asyncio.shield(fut), timeout=5)
            except asyncio.TimeoutError:
                log.warning("LISTEN %s not confirmed within 5 s (stream continues, may lag)", channel)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        s = self.subs.get(channel)
        if s is not None:
            s.discard(q)
            if not s:
                del self.subs[channel]
                self.cmds.append(("UNLISTEN", channel, None))
                # not listening any more -> the cache could go stale; drop it
                self.cache.pop(channel, None)
                self.gen.pop(channel, None)
                self.locks.pop(channel, None)

    async def snapshot(self, channel: str, game_id: Any, fresh: bool = False) -> Optional[dict]:
        want = self.gen.get(channel, 0)
        c = self.cache.get(channel)
        if c is not None and c[0] >= want and not fresh:
            return c[1]
        lock = self.locks.setdefault(channel, asyncio.Lock())
        async with lock:
            c = self.cache.get(channel)
            if c is not None and c[0] >= self.gen.get(channel, 0) and not fresh:
                return c[1]  # another stream fetched while we waited
            at = self.gen.get(channel, 0)
            self.fetches += 1
            data = await run_in_threadpool(_snapshot_by_id, game_id)
            if channel in self.subs:
                self.cache[channel] = (at, data)
            return data

    def subscriber_count(self, channel: str | None = None) -> int:
        if channel is None:
            return sum(len(s) for s in self.subs.values())
        return len(self.subs.get(channel, ()))

    def _dispatch(self, channel: str, payload: str) -> None:
        self.gen[channel] = self.gen.get(channel, 0) + 1
        for q in list(self.subs.get(channel, ())):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # the stream re-reads the full state anyway; one pending item is enough

    async def _run(self) -> None:
        while True:
            conn = None
            try:
                conn = await psycopg.AsyncConnection.connect(db.database_url(), autocommit=True,
                                                             connect_timeout=3)
                self.listening = set()
                for ch in list(self.subs):
                    await conn.execute(f"LISTEN {ch}")
                    self.listening.add(ch)
                    self._dispatch(ch, '{"reconnect": true}')  # we may have missed events
                self.connected.set()
                while True:
                    while self.cmds:
                        op, ch, fut = self.cmds.popleft()
                        if not re.fullmatch(r"live_[0-9a-f]{32}", ch):
                            continue
                        if op == "LISTEN" and ch not in self.listening:
                            await conn.execute(f"LISTEN {ch}")
                            self.listening.add(ch)
                        elif op == "UNLISTEN" and ch in self.listening and ch not in self.subs:
                            await conn.execute(f"UNLISTEN {ch}")
                            self.listening.discard(ch)
                        if fut is not None and not fut.done():
                            fut.set_result(True)
                    async for n in conn.notifies(timeout=self.POLL_SEC):
                        self._dispatch(n.channel, n.payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on any DB error
                self.connected.clear()
                log.warning("live broker connection lost (%s); reconnecting", exc)
                await asyncio.sleep(1)
            finally:
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:  # noqa: BLE001
                        pass


_brokers: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Broker]" = weakref.WeakKeyDictionary()


def get_broker() -> Broker:
    loop = asyncio.get_running_loop()
    b = _brokers.get(loop)
    if b is None:
        b = _brokers[loop] = Broker()
    return b


# --------------------------------------------------------------------------- helpers

def _num(v: Any) -> Any:
    return float(v) if isinstance(v, Decimal) else v


def _clean_nick(v: Any) -> str:
    if not isinstance(v, str):
        raise HTTPException(422, "nickname: must be a string")
    v = _SPACE_RE.sub(" ", _CTRL_RE.sub("", v)).strip()
    if not 1 <= len(v) <= NICK_MAX:
        raise HTTPException(422, f"nickname: must be 1-{NICK_MAX} characters")
    return v


def _check_pin(pin: str) -> None:
    if not PIN_RE.match(pin or ""):
        raise HTTPException(404, "Game not found")


def _candidates(conn, pin: str) -> list[dict]:
    """Games with this PIN: the live one first, then ended ones (newest first)."""
    _check_pin(pin)
    return conn.execute(
        """SELECT * FROM live_game WHERE pin = %s
            ORDER BY (status <> 'ended') DESC, created_at DESC LIMIT 20""",
        (pin,),
    ).fetchall()


def _host_game(conn, pin: str, token: Optional[str], lock: Optional[str] = None) -> dict:
    """Resolve the game this host token belongs to. 404 unknown PIN, 403 bad/missing token."""
    games = _candidates(conn, pin)
    if not games:
        raise HTTPException(404, "Game not found")
    match = None
    for g in games:  # constant-time compare against every candidate
        if token and secrets.compare_digest(g["host_token"].encode(), token.encode()):
            match = g
    if match is None:
        raise HTTPException(403, "Invalid or missing host token")
    if lock:
        match = conn.execute(f"SELECT * FROM live_game WHERE id = %s FOR {lock}", (match["id"],)).fetchone()
    return match


def _player(conn, pin: str, token: Optional[str]) -> tuple[dict, dict]:
    """(game, player) for a player token. 404 unknown PIN, 403 bad token or kicked."""
    games = _candidates(conn, pin)
    if not games:
        raise HTTPException(404, "Game not found")
    found = None
    if token:
        tok = token.encode()
        for g in games:
            for p in conn.execute("SELECT id, player_token FROM live_player WHERE game_id = %s",
                                  (g["id"],)).fetchall():
                if secrets.compare_digest(p["player_token"].encode(), tok):
                    found = (g, p["id"])
    if found is None:
        raise HTTPException(403, "Invalid or missing player token")
    g, pid = found
    p = conn.execute("SELECT id, game_id, nickname, score, streak, is_kicked FROM live_player WHERE id = %s",
                     (pid,)).fetchone()
    if p["is_kicked"]:
        raise HTTPException(403, "You were removed from this game")
    return g, p


def _question_view(q: dict) -> dict:
    mode = q["game_mode"]
    return {
        "idx": q["idx"], "game_mode": mode, "prompt": q["prompt"],
        "target_text": None,  # speaking-only field, kept in the shape for older clients
        "image_url": q["image_url"], "image_alt": q.get("image_alt"),
        "options": list(q["options"]) if mode == MC else None,
        "time_limit_sec": q["time_limit_sec"], "difficulty": q["difficulty"], "base_points": q["base_points"],
    }


def _correct_view(q: dict) -> dict:
    mode = q["game_mode"]
    if mode == MC:
        opts = list(q["options"])
        co = q["correct_option"]
        return {"option": co, "option_text": opts[co] if co is not None and 0 <= co < len(opts) else None}
    return {"option": None, "option_text": None}  # a legacy speaking question (never picked since 2026-09-28)


def _answer_result(a: dict) -> dict:
    fb = dict(a["feedback"] or {})
    fb.pop("stt_words", None)  # present on answers stored before speaking was removed
    return {"accuracy": _num(a["accuracy"]), "passed": a["passed"], "stars": a["stars"], "points": a["points"],
            "transcript": a["transcript"], "choice": a["choice"], "answer_ms": a["answer_ms"],
            "streak": fb.pop("streak", None), "speed_factor": fb.pop("speed_factor", None),
            "streak_multiplier": fb.pop("streak_multiplier", None), "feedback": fb}


# ONE ordered query over the game's players gives the whole leaderboard: current rank, rank at the start of the
# current question (score minus this question's APPLIED points) and whether each player answered it.
LEADERBOARD_SQL = """
SELECT p.id, p.nickname, p.score, p.streak, p.joined_at,
       (a.id IS NOT NULL) AS answered, COALESCE(a.applied, false) AS applied,
       RANK() OVER (ORDER BY p.score DESC)::int AS rank,
       RANK() OVER (ORDER BY p.score - CASE WHEN a.applied THEN a.points ELSE 0 END DESC)::int AS prev_rank
  FROM live_player p
  LEFT JOIN live_answer a ON a.game_id = p.game_id AND a.idx = %(idx)s AND a.player_id = p.id
 WHERE p.game_id = %(gid)s AND NOT p.is_kicked
 ORDER BY p.score DESC, lower(p.nickname), p.id
"""


def fetch_snapshot(conn, game_id: Any) -> Optional[dict]:
    """Everything any role's state needs, in 5 queries (independent of the number of players)."""
    g = conn.execute("SELECT *, clock_timestamp() AS now FROM live_game WHERE id = %s", (game_id,)).fetchone()
    if g is None:
        return None
    if g["mode"] == "self_paced":
        return sp.fetch_snapshot(conn, g)
    gid, idx = g["id"], g["current_index"]
    total = conn.execute("SELECT COUNT(*)::int AS n FROM live_question WHERE game_id = %s", (gid,)).fetchone()["n"]
    q = None
    if 0 <= idx < total:
        q = conn.execute(
            """SELECT lq.idx, q.game_mode, q.prompt, q.target_text, q.keywords, q.image_url, q.image_alt,
                      q.options, q.correct_option, q.time_limit_sec, q.difficulty, q.base_points
                 FROM live_question lq JOIN question q ON q.id = lq.question_id
                WHERE lq.game_id = %s AND lq.idx = %s""", (gid, idx)).fetchone()
    rows = conn.execute(LEADERBOARD_SQL, {"gid": gid, "idx": idx}).fetchall()
    answers = []
    if idx >= 0:
        answers = conn.execute(
            """SELECT a.* FROM live_answer a JOIN live_player p ON p.id = a.player_id AND NOT p.is_kicked
                WHERE a.game_id = %s AND a.idx = %s ORDER BY a.points DESC, a.answer_ms, a.id""",
            (gid, idx)).fetchall()
    answered_any = conn.execute(
        """SELECT COUNT(DISTINCT a.player_id)::int AS n FROM live_answer a
             JOIN live_player p ON p.id = a.player_id AND NOT p.is_kicked WHERE a.game_id = %s""",
        (gid,)).fetchone()["n"]
    return {"g": g, "total": total, "q": q, "rows": rows, "answers": answers, "answered_any": answered_any}


def render_state(snap: Optional[dict], role: Literal["host", "player"], me_id: Optional[int] = None) -> Optional[dict]:
    """LiveState for one role from a snapshot (pure). None = game gone / player not active (kicked).

    Secrets never leak: no tokens; keywords / correct option only from `reveal` on — except a player's OWN
    `last_result.correct` once their answer is scored (instant_feedback)."""
    if snap is None:
        return None
    if snap.get("sp"):
        return sp.render_state(snap, role, me_id)
    g, q, rows, answers = snap["g"], snap["q"], snap["rows"], snap["answers"]
    status, idx = g["status"], g["current_index"]
    in_round = status in ("question", "reveal", "leaderboard") and q is not None
    revealed = status in ("reveal", "leaderboard") and q is not None
    by_player = {a["player_id"]: a for a in answers}
    names = {r["id"]: r["nickname"] for r in rows}
    show_delta = idx > 0  # question 1: everybody started at 0, no rank change to show

    time_left_ms = None
    if status == "question" and q is not None and g["phase_started_at"] is not None:
        elapsed = (g["now"] - g["phase_started_at"]).total_seconds() * 1000
        time_left_ms = max(0, int(q["time_limit_sec"] * 1000 - elapsed))

    entries = [{"rank": r["rank"], "player_id": r["id"], "nickname": r["nickname"], "score": r["score"],
                "delta_rank": (r["prev_rank"] - r["rank"]) if show_delta else 0} for r in rows]

    state: dict[str, Any] = {
        "game_id": str(g["id"]), "pin": g["pin"], "status": status, "title": g["title"], "mode": "live",
        "index": idx, "total": snap["total"], "phase_started_at": g["phase_started_at"], "server_now": g["now"],
        "time_left_ms": time_left_ms,
        "settings": {"allow_rename": g["allow_rename"], "instant_feedback": g["instant_feedback"]},
        "question": _question_view(q) if in_round else None,
        "players_count": len(rows), "answered_count": len(answers),
    }

    if role == "host":
        state["players"] = [{"id": r["id"], "nickname": r["nickname"], "score": r["score"], "rank": r["rank"],
                             "answered": r["answered"], "joined_at": r["joined_at"]}
                            for r in sorted(rows, key=lambda r: (r["joined_at"], r["id"]))]
        state["reveal"] = None
        if revealed:
            dist = {"great": 0, "ok": 0, "retry": 0, "no_answer": len(rows) - len(answers)}
            for a in answers:
                if a["passed"] and a["stars"] >= 3:
                    dist["great"] += 1
                elif a["passed"]:
                    dist["ok"] += 1
                else:
                    dist["retry"] += 1
            if q["game_mode"] == MC:
                counts = [0] * len(q["options"])
                for a in answers:
                    if a["choice"] is not None and 0 <= a["choice"] < len(counts):
                        counts[a["choice"]] += 1
                dist["options"] = counts
            state["reveal"] = {
                "correct": _correct_view(q), "distribution": dist,
                "top": [{"nickname": names[a["player_id"]], "points": a["points"]}
                        for a in answers if a["points"] > 0][:3],
                "answers": [{"player_id": a["player_id"], "nickname": names[a["player_id"]],
                             **{k: v for k, v in _answer_result(a).items() if k != "feedback"}}
                            for a in answers],
            }
        state["leaderboard"] = {
            "top": entries[:TOP_N],
            # animation hint: rank moves since the start of the current question
            "rank_changes": [{"player_id": r["id"], "nickname": r["nickname"], "from": r["prev_rank"],
                              "to": r["rank"]} for r in rows if show_delta and r["prev_rank"] != r["rank"]],
        }
        state["summary"] = {"joined": len(rows), "answered_any": snap["answered_any"]}
        return state

    pos = next((i for i, r in enumerate(rows) if r["id"] == me_id), None)
    if pos is None:
        return None
    me = rows[pos]
    mine = by_player.get(me_id)
    last = None
    if mine is not None and mine["applied"] and q is not None:
        last = {**_answer_result(mine), "correct": _correct_view(q)}
    above = rows[pos - 1] if pos > 0 else None
    state["me"] = {"id": me["id"], "nickname": me["nickname"], "score": me["score"], "rank": me["rank"],
                   "streak": me["streak"], "answered_current": mine is not None, "last_result": last}
    state["reveal"] = {"correct": _correct_view(q)} if revealed else None
    state["leaderboard"] = {
        "top": [{k: e[k] for k in ("rank", "nickname", "score", "delta_rank")} for e in entries[:TOP_N]],
        "me": {"rank": me["rank"], "score": me["score"],
               "above": None if above is None else {"nickname": above["nickname"],
                                                    "score_gap": above["score"] - me["score"]}},
    }
    return state


def build_state(conn, g: dict, role: Literal["host", "player"], me_id: Optional[int] = None) -> Optional[dict]:
    return render_state(fetch_snapshot(conn, g["id"]), role, me_id)


def _host_state(pin: str, token: Optional[str]) -> dict:
    with db.connection() as conn:
        return build_state(conn, _host_game(conn, pin, token), "host")


def _player_state(pin: str, token: Optional[str]) -> dict:
    with db.connection() as conn:
        g, p = _player(conn, pin, token)
        if g["mode"] == "self_paced":
            g = sp.touch_player(conn, g, p["id"])  # lazy auto-close + expiry of a timed-out question
        return build_state(conn, g, "player", p["id"])


def _snapshot_by_id(game_id: UUID) -> Optional[dict]:
    with db.connection() as conn:
        return fetch_snapshot(conn, game_id)


def _apply_pending(conn, game_id: Any, idx: int) -> int:
    """Add not-yet-applied answers of question `idx` to their players — exactly once (applied flag flips in the
    same statement). Called when a question closes, on /end during a question, and when instant_feedback is
    switched on mid-question. Caller holds the live_game row lock (FOR UPDATE)."""
    return len(conn.execute(
        """WITH app AS (
               UPDATE live_answer SET applied = true
                WHERE game_id = %s AND idx = %s AND NOT applied
            RETURNING player_id, points, feedback)
           UPDATE live_player p SET score = p.score + app.points,
                  streak = COALESCE((app.feedback->>'streak')::int, 0)
             FROM app WHERE p.id = app.player_id
           RETURNING p.id""",
        (game_id, idx)).fetchall())


# --------------------------------------------------------------------------- models

class GameIn(BaseModel):
    pack_id: Optional[int] = None
    game_modes: list[str] = Field(default_factory=lambda: list(DEFAULT_MODES), min_length=1)
    question_count: int = Field(default=10, ge=1, le=30)
    title: Optional[str] = Field(default="", max_length=120)
    teacher_name: Optional[str] = Field(default="", max_length=120)
    school: Optional[str] = Field(default="", max_length=200)
    program: Optional[str] = Field(default="", max_length=120)
    allow_rename: bool = True       # players may change their own nickname (PATCH /me)
    instant_feedback: bool = True   # score at submit + live leaderboard (False = Kahoot-like, at reveal)
    # self-paced / homework (CONTRACT "SELF-PACED / HOMEWORK MODE")
    mode: Literal["live", "self_paced"] = "live"
    closes_at: Optional[datetime] = None        # self_paced only: future, <= 30 days (naive = UTC)
    speed_bonus: Optional[bool] = None          # default: true for live, false for self_paced
    shuffle_per_player: bool = False            # self_paced only: each player gets their own order at join

    @field_validator("closes_at")
    @classmethod
    def _aware(cls, v: Optional[datetime]) -> Optional[datetime]:
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v

    @field_validator("game_modes")
    @classmethod
    def _mc_only(cls, v: list) -> list:
        v = list(dict.fromkeys(v))
        if any(m != MC for m in v):
            raise ValueError(f"{SPEAKING_UNSUPPORTED} (only {MC!r})")
        return v

    @field_validator("title", "teacher_name", "school", "program")
    @classmethod
    def _txt(cls, v: Optional[str]) -> str:
        return _SPACE_RE.sub(" ", v or "").strip()


class JoinIn(BaseModel):
    nickname: str


class RenameIn(BaseModel):
    nickname: str


class SettingsIn(BaseModel):
    allow_rename: Optional[bool] = None
    instant_feedback: Optional[bool] = None
    # self_paced only (sent on a live game -> 422); closes_at: null clears the deadline, past = close now
    paused: Optional[bool] = None
    closes_at: Optional[datetime] = None

    @field_validator("closes_at")
    @classmethod
    def _aware(cls, v: Optional[datetime]) -> Optional[datetime]:
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v


class NextIn(BaseModel):
    """The phase the host UI is looking at; a stale click (double-click) then gets 409 instead of skipping."""
    status: Optional[Literal["lobby", "question", "reveal", "leaderboard", "ended"]] = None
    index: Optional[int] = None


# --------------------------------------------------------------------------- routes: setup

@router.get("/packs")
def list_packs(x_edit_key: Optional[str] = Header(default=None)):
    """Seeded packs (editable: false) + the teacher's own quizzes whose edit key is sent in X-Edit-Key
    (comma-separated for several), with playable question counts per type."""
    from . import quiz  # lazy: quiz imports this module
    return quiz.list_packs_for(quiz.split_keys(x_edit_key))


def _create_game(body: GameIn, base_url: str) -> dict:
    self_paced = body.mode == "self_paced"
    if not self_paced and body.closes_at is not None:
        raise HTTPException(422, "closes_at: only for mode self_paced")
    if not self_paced and body.shuffle_per_player:
        raise HTTPException(422, "shuffle_per_player: only for mode self_paced")
    speed_bonus = (not self_paced) if body.speed_bonus is None else body.speed_bonus
    instant_feedback = True if self_paced else body.instant_feedback  # self-paced always scores at submit
    with db.connection() as conn:
        if body.closes_at is not None:
            sp.check_deadline(conn, body.closes_at, must_be_future=True)
        pack = None
        if body.pack_id is not None:
            pack = conn.execute(
                "SELECT id, name, is_active, edit_key_hash IS NOT NULL AS teacher_owned "
                "FROM question_pack WHERE id = %s",
                (body.pack_id,)).fetchone()
            if not pack:
                raise HTTPException(404, f"Pack {body.pack_id} not found")
            if not pack["is_active"]:
                raise HTTPException(422, f"Pack {body.pack_id} is archived")
        # A teacher's own quiz plays in the order the teacher set; ready-made packs are shuffled.
        order_sql = "q.sort_order, q.id" if pack and pack["teacher_owned"] else "random()"
        qs = conn.execute(
            f"""SELECT q.id FROM question q
                 WHERE q.is_active AND (%s::bigint IS NULL OR q.pack_id = %s::bigint) AND {PLAYABLE_SQL}
                   AND (%s::bigint IS NOT NULL OR {NOT_PRIVATE_SQL})
                 ORDER BY {order_sql} LIMIT %s""",
            (body.pack_id, body.pack_id, body.pack_id, body.question_count),
        ).fetchall()
        if len(qs) < body.question_count:
            raise HTTPException(422, f"Not enough questions: {len(qs)} available for "
                                     f"{MC}, {body.question_count} requested")
        title = body.title or (pack["name"] if pack else "Live quiz")
        host_token = secrets.token_urlsafe(32)
        g = None
        for _ in range(20):
            pin = f"{secrets.randbelow(900000) + 100000}"
            try:
                with conn.transaction():  # savepoint: a PIN collision only retries this insert
                    g = conn.execute(
                        """INSERT INTO live_game (pin, host_token, title, teacher_name, school, program, pack_id,
                                                  allow_rename, instant_feedback, mode, status, closes_at,
                                                  speed_bonus, shuffle_per_player, phase_started_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                   CASE WHEN %s THEN clock_timestamp() END)
                        RETURNING id, pin, closes_at""",
                        (pin, host_token, title, body.teacher_name, body.school, body.program, body.pack_id,
                         body.allow_rename, instant_feedback, body.mode, "open" if self_paced else "lobby",
                         body.closes_at, speed_bonus, body.shuffle_per_player, self_paced),
                    ).fetchone()
                break
            except psycopg.errors.UniqueViolation:
                continue
        if g is None:
            raise HTTPException(503, "Could not allocate a game PIN, try again")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO live_question (game_id, idx, question_id) VALUES (%s, %s, %s)",
                            [(g["id"], i, q["id"]) for i, q in enumerate(qs)])
    base = os.environ.get("LIVE_PUBLIC_URL", base_url).rstrip("/")
    return {"game_id": str(g["id"]), "pin": g["pin"], "host_token": host_token,
            "join_url": f"{base}/play?pin={g['pin']}", "title": title, "total": len(qs),
            **({"mode": body.mode, "closes_at": g["closes_at"]} if self_paced else {})}


@router.post("/games", status_code=201)
async def create_game(body: GameIn, request: Request):
    for attempt in range(3):
        try:
            return await run_in_threadpool(_create_game, body, str(request.base_url))
        except psycopg.errors.ForeignKeyViolation:  # a picked question was deleted by its teacher meanwhile
            if attempt == 2:
                raise HTTPException(409, "Quiz changed while creating the game, try again")


@router.get("/games/{pin}")
def game_lookup(pin: str, request: Request):
    """Public PIN check for the join screen: no secrets, rate limited like join."""
    if not lookup_limiter.hit(_client_ip(request)):
        raise HTTPException(429, "Too many requests, wait a few seconds")
    with db.connection() as conn:
        games = _candidates(conn, pin)
        if games and games[0]["mode"] == "self_paced":
            games[0] = sp.autoclose(conn, games[0])
    if not games:
        raise HTTPException(404, "Game not found")
    g = games[0]
    out = {"pin": g["pin"], "title": g["title"], "status": g["status"], "joinable": g["status"] != "ended"}
    if g["mode"] == "self_paced":
        out.update(joinable=g["status"] != "ended" and not g["paused"], mode=g["mode"], paused=g["paused"],
                   closes_at=g["closes_at"])
    return out


# --------------------------------------------------------------------------- routes: state + SSE

@router.get("/games/{pin}/state")
def get_state(pin: str, host_token: Optional[str] = None, player_token: Optional[str] = None,
              x_host_token: Optional[str] = Header(default=None),
              x_player_token: Optional[str] = Header(default=None)):
    host_token = host_token or x_host_token
    player_token = player_token or x_player_token
    if host_token:
        return _host_state(pin, host_token)
    if player_token:
        return _player_state(pin, player_token)
    with db.connection() as conn:
        if not _candidates(conn, pin):
            raise HTTPException(404, "Game not found")
    raise HTTPException(403, "host_token or player_token required")


def _stream_auth(pin: str, host_token: Optional[str], player_token: Optional[str]) -> tuple[UUID, str, Optional[int]]:
    with db.connection() as conn:
        if host_token:
            return _host_game(conn, pin, host_token)["id"], "host", None
        if player_token:
            g, p = _player(conn, pin, player_token)
            return g["id"], "player", p["id"]
        if not _candidates(conn, pin):
            raise HTTPException(404, "Game not found")
    raise HTTPException(403, "host_token or player_token required")


def _sse(event: str, data: Any, event_id: Optional[str] = None) -> str:
    body = json.dumps(jsonable_encoder(data), separators=(",", ":"), ensure_ascii=False)
    return (f"id: {event_id}\n" if event_id else "") + f"event: {event}\ndata: {body}\n\n"


_VOLATILE = ("server_now", "time_left_ms")


@router.get("/games/{pin}/events")
async def events(pin: str, request: Request, host_token: Optional[str] = None,
                 player_token: Optional[str] = None):
    game_id, role, player_id = await run_in_threadpool(_stream_auth, pin, host_token, player_token)
    channel = channel_for(game_id)
    broker = get_broker()
    queue = await broker.subscribe(channel)

    async def gen():
        last_key = None
        version = None
        last_push = 0.0
        force = False
        try:
            yield "retry: 2000\n\n"
            while True:
                snap = await broker.snapshot(channel, game_id, fresh=force)
                force = False
                state = render_state(snap, role, player_id)
                if state is None and snap is not None:
                    # maybe a cached snapshot from before this player's join / a rename: re-read once
                    state = render_state(await broker.snapshot(channel, game_id, fresh=True), role, player_id)
                if state is None:
                    yield _sse("kicked", {"detail": "You were removed from this game"})
                    return
                key = json.dumps(jsonable_encoder({k: v for k, v in state.items() if k not in _VOLATILE}),
                                 sort_keys=True)
                if key != last_key:
                    last_key = key
                    last_push = time.monotonic()
                    yield _sse("state", state, version)
                # Wait for the next NOTIFY; heartbeat comment every HEARTBEAT_SEC; notice disconnects early.
                waited = 0.0
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                        # throttle: <= 1 push per PUSH_MIN_INTERVAL; everything arriving meanwhile is coalesced
                        await asyncio.sleep(max(0.05, PUSH_MIN_INTERVAL - (time.monotonic() - last_push)))
                        while not queue.empty():
                            payload = queue.get_nowait()
                        try:
                            version = str(json.loads(payload).get("v") or "") or version
                        except (ValueError, AttributeError):
                            pass
                        break
                    except asyncio.TimeoutError:
                        waited += 1.0
                        if await request.is_disconnected():
                            return
                        if sp.deadline_passed(state):  # self-paced deadline: a fresh read auto-closes the game
                            force = True
                            break
                        if waited >= HEARTBEAT_SEC:
                            waited = 0.0
                            yield ": ping\n\n"
        finally:
            broker.unsubscribe(channel, queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- routes: join

def _join(pin: str, nickname: str) -> dict:
    with db.connection() as conn:
        games = _candidates(conn, pin)
        if not games:
            raise HTTPException(404, "Game not found")
        g = games[0]
        if g["status"] == "ended":
            raise HTTPException(409, "This game has ended")
        g = conn.execute("SELECT * FROM live_game WHERE id = %s FOR UPDATE", (g["id"],)).fetchone()
        if g["mode"] == "self_paced":
            g = sp.join_checks(conn, g)  # auto-close, 409 ended / paused
        if g["status"] == "ended":
            raise HTTPException(409, "This game has ended")
        if conn.execute("SELECT 1 FROM live_player WHERE game_id = %s AND lower(nickname) = lower(%s)",
                        (g["id"], nickname)).fetchone():
            raise HTTPException(409, "name taken")
        token = secrets.token_urlsafe(32)
        try:
            with conn.transaction():
                p = conn.execute(
                    "INSERT INTO live_player (game_id, nickname, player_token, question_order) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (g["id"], nickname, token,
                     sp.question_order_for(conn, g) if g["mode"] == "self_paced" else None)).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "name taken")
        notify(conn, g["id"])
    return {"player_id": p["id"], "player_token": token, "nickname": nickname, "game_id": str(g["id"])}


@router.post("/games/{pin}/join", status_code=201)
async def join(pin: str, body: JoinIn, request: Request):
    if not join_limiter.hit(_client_ip(request)):
        raise HTTPException(429, "Too many join attempts, wait a few seconds")
    nickname = _clean_nick(body.nickname)
    return await run_in_threadpool(_join, pin, nickname)


# --------------------------------------------------------------------------- routes: host actions

def _host_action(pin: str, token: Optional[str], fn) -> dict:
    with db.connection() as conn:
        g = _host_game(conn, pin, token, lock="UPDATE")
        if g["mode"] == "self_paced":
            g = sp.autoclose(conn, g)
        changed = fn(conn, g)
        if changed is not False:
            notify(conn, g["id"])
        g = conn.execute("SELECT * FROM live_game WHERE id = %s", (g["id"],)).fetchone()
        return build_state(conn, g, "host")


def _do_start(conn, g: dict):
    if g["mode"] == "self_paced":
        raise HTTPException(409, "Self-paced game: players start on their own")
    if g["status"] != "lobby":
        raise HTTPException(409, f"Game already started (status {g['status']})")
    total = conn.execute("SELECT COUNT(*)::int AS n FROM live_question WHERE game_id = %s",
                         (g["id"],)).fetchone()["n"]
    if total == 0:
        raise HTTPException(409, "Game has no questions")
    conn.execute("UPDATE live_game SET status = 'question', current_index = 0, phase_started_at = clock_timestamp() "
                 "WHERE id = %s", (g["id"],))


def _make_next(body: Optional[NextIn]):
    def _do_next(conn, g: dict):
        if g["mode"] == "self_paced":
            raise HTTPException(409, "Self-paced game: players move at their own pace")
        if body is not None and body.status is not None and body.status != g["status"]:
            raise HTTPException(409, f"Stale: game is in {g['status']}, not {body.status}")
        if body is not None and body.index is not None and body.index != g["current_index"]:
            raise HTTPException(409, f"Stale: current index is {g['current_index']}, not {body.index}")
        if g["status"] == "lobby":
            raise HTTPException(409, "Game not started yet (use /start)")
        if g["status"] == "ended":
            raise HTTPException(409, "Game has ended")
        if (body is None or (body.status is None and body.index is None)) and g["phase_started_at"] is not None:
            age = conn.execute("SELECT (EXTRACT(EPOCH FROM clock_timestamp() - %s::timestamptz) * 1000)::int AS ms",
                               (g["phase_started_at"],)).fetchone()["ms"]
            if age < NEXT_DEBOUNCE_MS:
                raise HTTPException(409, "Next pressed twice; ignored")
        total = conn.execute("SELECT COUNT(*)::int AS n FROM live_question WHERE game_id = %s",
                             (g["id"],)).fetchone()["n"]
        if g["status"] == "question":
            _apply_pending(conn, g["id"], g["current_index"])
            new, idx = "reveal", g["current_index"]
        elif g["status"] == "reveal":
            new, idx = "leaderboard", g["current_index"]
        elif g["current_index"] + 1 < total:  # leaderboard -> next question
            new, idx = "question", g["current_index"] + 1
        else:
            new, idx = "ended", g["current_index"]
        conn.execute(
            """UPDATE live_game SET status = %s, current_index = %s, phase_started_at = clock_timestamp(),
                      ended_at = CASE WHEN %s = 'ended' THEN clock_timestamp() ELSE ended_at END
                WHERE id = %s""",
            (new, idx, new, g["id"]))
    return _do_next


def _do_end(conn, g: dict):
    if g["status"] == "ended":
        return False  # idempotent
    if g["status"] == "question":
        _apply_pending(conn, g["id"], g["current_index"])
    conn.execute("UPDATE live_game SET status = 'ended', ended_at = clock_timestamp(), "
                 "phase_started_at = clock_timestamp() WHERE id = %s", (g["id"],))


@router.post("/games/{pin}/start")
def start_game(pin: str, x_host_token: Optional[str] = Header(default=None)):
    return _host_action(pin, x_host_token, _do_start)


@router.post("/games/{pin}/next")
def next_phase(pin: str, body: Optional[NextIn] = None, x_host_token: Optional[str] = Header(default=None)):
    return _host_action(pin, x_host_token, _make_next(body))


@router.post("/games/{pin}/end")
def end_game(pin: str, x_host_token: Optional[str] = Header(default=None)):
    return _host_action(pin, x_host_token, _do_end)


def _game_player(conn, g: dict, player_id: int) -> dict:
    p = conn.execute("SELECT * FROM live_player WHERE id = %s AND game_id = %s FOR UPDATE",
                     (player_id, g["id"])).fetchone()
    if not p:
        raise HTTPException(404, "Player not found")
    return p


@router.post("/games/{pin}/players/{player_id}/kick")
def kick_player(pin: str, player_id: int, x_host_token: Optional[str] = Header(default=None)):
    def _do(conn, g):
        p = _game_player(conn, g, player_id)  # allowed in every phase (also after end: cleans the report)
        if p["is_kicked"]:
            return False
        conn.execute("UPDATE live_player SET is_kicked = true WHERE id = %s", (player_id,))
    return _host_action(pin, x_host_token, _do)


@router.patch("/games/{pin}/players/{player_id}")
def rename_player(pin: str, player_id: int, body: RenameIn, x_host_token: Optional[str] = Header(default=None)):
    nickname = _clean_nick(body.nickname)

    def _do(conn, g):
        p = _game_player(conn, g, player_id)
        if p["is_kicked"]:
            raise HTTPException(404, "Player not found")
        if p["nickname"] == nickname:
            return False
        if conn.execute("SELECT 1 FROM live_player WHERE game_id = %s AND lower(nickname) = lower(%s) AND id <> %s",
                        (g["id"], nickname, player_id)).fetchone():
            raise HTTPException(409, "name taken")
        try:
            with conn.transaction():
                conn.execute("UPDATE live_player SET nickname = %s WHERE id = %s", (nickname, player_id))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "name taken")
    return _host_action(pin, x_host_token, _do)


@router.patch("/games/{pin}/settings")
def update_settings(pin: str, body: SettingsIn, x_host_token: Optional[str] = Header(default=None)):
    """Host toggles. Switching instant_feedback ON mid-question applies the answers stored so far (exactly once);
    switching it OFF only affects later answers (already-applied points stay)."""
    def _do(conn, g):
        if g["mode"] == "self_paced":
            return sp.update_settings(conn, g, body)
        if {"paused", "closes_at"} & body.model_fields_set:
            raise HTTPException(422, "paused / closes_at: only for self-paced games")
        changes = {k: v for k, v in body.model_dump(include={"allow_rename", "instant_feedback"}).items()
                   if v is not None and v != g[k]}
        if not changes:
            return False
        conn.execute("UPDATE live_game SET allow_rename = %s, instant_feedback = %s WHERE id = %s",
                     (changes.get("allow_rename", g["allow_rename"]),
                      changes.get("instant_feedback", g["instant_feedback"]), g["id"]))
        if changes.get("instant_feedback") is True and g["status"] == "question":
            _apply_pending(conn, g["id"], g["current_index"])
    return _host_action(pin, x_host_token, _do)


@router.patch("/games/{pin}/me")
def rename_me(pin: str, body: RenameIn, x_player_token: Optional[str] = Header(default=None)):
    """Player changes their own nickname (any phase except ended). Answers/score stay on the player id."""
    nickname = _clean_nick(body.nickname)
    with db.connection() as conn:
        g, p = _player(conn, pin, x_player_token)
        g = conn.execute("SELECT * FROM live_game WHERE id = %s FOR UPDATE", (g["id"],)).fetchone()
        if g["mode"] == "self_paced":
            g = sp.autoclose(conn, g)
        if g["status"] == "ended":
            raise HTTPException(409, "Game has ended")
        if not g["allow_rename"]:
            raise HTTPException(403, "renaming locked by teacher")
        p = conn.execute(
            """SELECT id, nickname, is_kicked,
                      (renamed_at IS NOT NULL AND clock_timestamp() - renamed_at < make_interval(secs => %s))
                          AS cooling
                 FROM live_player WHERE id = %s FOR UPDATE""", (RENAME_COOLDOWN_SEC, p["id"])).fetchone()
        if p["is_kicked"]:
            raise HTTPException(403, "You were removed from this game")
        if p["nickname"] != nickname:
            if p["cooling"]:
                raise HTTPException(429, f"You can change your name once every {RENAME_COOLDOWN_SEC} seconds")
            if conn.execute("SELECT 1 FROM live_player WHERE game_id = %s AND lower(nickname) = lower(%s) "
                            "AND id <> %s", (g["id"], nickname, p["id"])).fetchone():
                raise HTTPException(409, "name taken")
            try:
                with conn.transaction():
                    conn.execute("UPDATE live_player SET nickname = %s, renamed_at = clock_timestamp() WHERE id = %s",
                                 (nickname, p["id"]))
            except psycopg.errors.UniqueViolation:
                raise HTTPException(409, "name taken")
            notify(conn, g["id"])
        return build_state(conn, g, "player", p["id"])


# --------------------------------------------------------------------------- routes: answer

def _answer_precheck(pin: str, token: Optional[str], client_idx: Optional[int]) -> dict:
    """Auth + phase + time checks BEFORE STT. answer_ms is measured here (server clock at receipt)."""
    with db.connection() as conn:
        g, p = _player(conn, pin, token)
        if g["mode"] == "self_paced":
            ctx = sp.answer_precheck(conn, g, p, client_idx)  # errors returned, raised after commit
        else:
            return _live_answer_precheck(conn, g, p, client_idx)
    if "error" in ctx:
        raise ctx["error"].http()
    return ctx


def _live_answer_precheck(conn, g: dict, p: dict, client_idx: Optional[int]) -> dict:
    """Live-mode answer checks (unchanged): phase, idx, time limit + grace, one answer per question."""
    if g["status"] != "question":
        raise HTTPException(409, "Not accepting answers now")
    idx = g["current_index"]
    if client_idx is not None and client_idx != idx:
        raise HTTPException(409, f"Question {client_idx} is closed (current is {idx})")
    q = conn.execute(
        """SELECT q.game_mode, q.target_text, q.keywords, q.options, q.correct_option, q.difficulty,
                  q.base_points, q.time_limit_sec, q.prompt, q.image_url, lq.idx
             FROM live_question lq JOIN question q ON q.id = lq.question_id
            WHERE lq.game_id = %s AND lq.idx = %s""", (g["id"], idx)).fetchone()
    elapsed = conn.execute(
        "SELECT (EXTRACT(EPOCH FROM clock_timestamp() - %s::timestamptz) * 1000)::int AS ms",
        (g["phase_started_at"],)).fetchone()["ms"]
    if elapsed > q["time_limit_sec"] * 1000 + GRACE_MS:
        raise HTTPException(409, "Time is up")
    if conn.execute("SELECT 1 FROM live_answer WHERE game_id = %s AND idx = %s AND player_id = %s",
                    (g["id"], idx, p["id"])).fetchone():
        raise HTTPException(409, "Already answered")
    return {"game_id": g["id"], "idx": idx, "player_id": p["id"], "answer_ms": max(0, elapsed), "q": q}


def _record_answer(ctx: dict, result: dict, choice: Optional[int]) -> Optional[dict]:
    """Store the answer; with instant_feedback also add it to the player's score/streak in the SAME transaction
    (applied = true), else it is applied when the question closes. Returns the player's result when instant."""
    if ctx.get("mode") == "self_paced":
        return sp.record_answer(ctx, result, choice)
    q = ctx["q"]
    with db.connection() as conn:
        g = conn.execute("SELECT * FROM live_game WHERE id = %s FOR SHARE", (ctx["game_id"],)).fetchone()
        if g["status"] != "question" or g["current_index"] != ctx["idx"]:
            raise HTTPException(409, "Not accepting answers now")
        p = conn.execute("SELECT id, streak, is_kicked FROM live_player WHERE id = %s FOR UPDATE",
                         (ctx["player_id"],)).fetchone()
        if p["is_kicked"]:
            raise HTTPException(403, "You were removed from this game")
        if conn.execute("SELECT 1 FROM live_answer WHERE game_id = %s AND idx = %s AND player_id = %s",
                        (ctx["game_id"], ctx["idx"], p["id"])).fetchone():
            raise HTTPException(409, "Already answered")
        streak = scoring.next_streak(p["streak"], result["passed"])
        pts = scoring.live_points(base_points=q["base_points"], difficulty=q["difficulty"],
                                  accuracy=result["accuracy"], passed=result["passed"],
                                  answer_ms=ctx["answer_ms"] if g["speed_bonus"] else 0,
                                  time_limit_sec=q["time_limit_sec"], streak=streak)
        fb = {**result["feedback"], "streak": streak, "speed_factor": pts["speed_factor"],
              "streak_multiplier": pts["streak_multiplier"]}
        instant = bool(g["instant_feedback"])
        try:
            with conn.transaction():
                a = conn.execute(
                    """INSERT INTO live_answer (game_id, idx, player_id, transcript, choice, accuracy, passed,
                                                stars, points, answer_ms, feedback, applied)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                    (ctx["game_id"], ctx["idx"], p["id"], "", choice, result["accuracy"],
                     result["passed"], result["stars"], pts["points"], ctx["answer_ms"], Jsonb(fb),
                     instant)).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "Already answered")
        if instant:
            conn.execute("UPDATE live_player SET score = score + %s, streak = %s WHERE id = %s",
                         (pts["points"], streak, p["id"]))
        notify(conn, ctx["game_id"])
    if not instant:
        return None
    return {**_answer_result(a), "correct": _correct_view(q)}


def _as_int(v: Any, field: str) -> Optional[int]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise HTTPException(422, f"{field}: must be an integer")
    try:
        if isinstance(v, float) and not v.is_integer():
            raise ValueError
        return int(v)
    except (TypeError, ValueError):
        raise HTTPException(422, f"{field}: must be an integer")


@router.post("/games/{pin}/answer")
async def answer(pin: str, request: Request, x_player_token: Optional[str] = Header(default=None)):
    """JSON (or form) `{choice, idx?}` for a multiple_choice question. Audio uploads and speaking questions are
    rejected with 422 "speaking questions are not supported"."""
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(422, "Invalid JSON body")
        if not isinstance(data, dict):
            raise HTTPException(422, "JSON body must be an object")
    elif "multipart/form-data" in ctype or "application/x-www-form-urlencoded" in ctype:
        form = await request.form()
        if any(isinstance(v, StarletteUploadFile) for v in form.values()):
            raise HTTPException(422, SPEAKING_UNSUPPORTED)
        data = dict(form.items())
    else:
        raise HTTPException(422, "Send JSON {choice}")

    client_idx = _as_int(data.get("idx"), "idx")
    ctx = await run_in_threadpool(_answer_precheck, pin, x_player_token, client_idx)
    q = ctx["q"]
    if q["game_mode"] != MC:
        raise HTTPException(422, SPEAKING_UNSUPPORTED)
    choice = _as_int(data.get("choice"), "choice")
    n = len(q["options"])
    if choice is None or not 0 <= choice < n:
        raise HTTPException(422, f"choice: required, 0..{n - 1}")
    result = scoring.score_multiple_choice(choice, q["correct_option"])
    mine = await run_in_threadpool(_record_answer, ctx, result, choice)
    return {"accepted": True, "result": mine, **ctx.get("after", {})}


# --------------------------------------------------------------------------- routes: report

CSV_COLS = ["pin", "title", "date", "teacher_name", "school", "program", "pack", "questions",
            "nickname", "answered", "correct", "avg_accuracy", "score", "rank"]
CSV_SP_COLS = ["progress", "finished_at"]  # self-paced only: "<completed>/<total>", ISO timestamp or empty


@router.get("/games/{pin}/report.csv")
def report_csv(pin: str, host_token: Optional[str] = None, x_host_token: Optional[str] = Header(default=None)):
    with db.connection() as conn:
        g = _host_game(conn, pin, host_token or x_host_token)
        meta = conn.execute(
            """SELECT g.created_at::date AS date, p.name AS pack,
                      (SELECT COUNT(*)::int FROM live_question lq WHERE lq.game_id = g.id) AS questions
                 FROM live_game g LEFT JOIN question_pack p ON p.id = g.pack_id WHERE g.id = %s""",
            (g["id"],)).fetchone()
        rows = conn.execute(
            """SELECT p.id, p.nickname, p.score, p.current_idx, p.finished_at,
                      COUNT(a.id)::int AS answered,
                      COUNT(a.id) FILTER (WHERE a.passed)::int AS correct,
                      ROUND(AVG(a.accuracy), 2) AS avg_accuracy
                 FROM live_player p LEFT JOIN live_answer a ON a.player_id = p.id
                WHERE p.game_id = %s AND NOT p.is_kicked
                GROUP BY p.id ORDER BY p.score DESC, lower(p.nickname), p.id""",
            (g["id"],)).fetchall()
    scores = [r["score"] for r in rows]
    ranks = {r["id"]: 1 + sum(1 for x in scores if x > r["score"]) for r in rows}
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, lineterminator="\r\n")
    homework = g["mode"] == "self_paced"
    w.writerow(CSV_COLS + (CSV_SP_COLS if homework else []))
    for r in rows:
        w.writerow([g["pin"], g["title"], meta["date"].isoformat(), g["teacher_name"], g["school"], g["program"],
                    meta["pack"] or "", meta["questions"], r["nickname"], r["answered"], r["correct"],
                    "" if r["avg_accuracy"] is None else f"{float(r['avg_accuracy']):.2f}",
                    r["score"], ranks[r["id"]]]
                   + ([f"{min(r['current_idx'], meta['questions'])}/{meta['questions']}",
                       r["finished_at"].isoformat() if r["finished_at"] else ""] if homework else []))
    fname = f"{'homework' if homework else 'live'}-{meta['date'].isoformat()}-{g['pin']}.csv"
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# --------------------------------------------------------------------------- self-paced / homework mode
# Registers POST /games/{pin}/me/start on this router; the functions above dispatch to it on mode = 'self_paced'.
from . import live_self_paced as sp  # noqa: E402
