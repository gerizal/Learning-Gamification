# PlayClass — Local Setup Guide

PlayClass is a Kahoot-style classroom quiz by Solve Education. A teacher hosts a quiz. Students either join with a PIN on
their own devices, play as **homework** at their own pace, or answer while the **teacher presents** (no student devices;
individuals or groups). Scores are calculated on the server, and the leaderboard updates live.

For the product brief, see [`README.md`](../README.md). To deploy on AWS, see [`DEPLOY-EC2.md`](DEPLOY-EC2.md).

---

## 1. Requirements

- Python 3.11 or 3.12
- PostgreSQL 16 client and server binaries (`initdb`, `pg_ctl`, `psql`). On macOS: `brew install postgresql@16`
- Chrome, Edge or Firefox

## 2. Quick start

```bash
cd apps/game-console              # or wherever this folder lives
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
./scripts/dev_db.sh               # local Postgres on port 55432 (data in ./.pgdata), applies db/*.sql
./scripts/run.sh                  # http://localhost:8000 (auto-reload)
```

To stop the database, run `./scripts/dev_db.sh stop`.

PlayClass is a multiple-choice quiz only. There is no speaking mode, no speech model and no admin page.

## 3. Pages

| URL | Who | What |
|---|---|---|
| `/` | everyone | Gate: **I'm a Teacher** / **I'm a Student** |
| `/host` | teacher | Choose or create a quiz, pick how students play, host the game (PIN, lobby, questions, leaderboard, podium, CSV) |
| `/play` | student | Enter the PIN and a nickname, then answer. Instant results and a live rank. Nickname can be changed at any time |
| `/classroom` | teacher | Teacher presents, with no student devices. **Individuals** or **Groups**, with the projector stage |
| `/reports` | program team | School, game and student reports and CSV exports. Needs the access code |

`/reports` needs `REPORTS_KEY`. The app has **no default**: without it, `/reports` says "Reports are not set up on this
server yet" and `/api/reports/*` answers 503. For local development only, `./scripts/run.sh` sets
`REPORTS_KEY=reports123` when you have not set it yourself.

**Try it on one laptop:** open `/host` in one window. Open `/play` in a private or incognito window for each extra student.
To use phones on the same Wi-Fi, run
`./scripts/run.sh --host 0.0.0.0` and open `http://<laptop-ip>:8000`.

## 4. Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://localhost:55432/playclass` (via `run.sh`) | Postgres connection string |
| `REPORTS_KEY` | **none (required)** | Access code for `/reports`. Unset → `/api/reports/*` answers 503 "reports not configured" and a warning is logged at startup. `run.sh` sets `reports123` for local dev only |
| `LIVE_PUBLIC_URL` | request host | Base URL used in the join links shown to teachers |
| `LIVE_JOIN_LIMIT` / `LIVE_JOIN_WINDOW_SEC` | 10 / 10 | Join rate limit per IP. Raise it for classes behind one NAT |
| `QUIZ_CREATE_LIMIT` | 20 per hour | Teacher quiz creations per IP |
| `REPORTS_FAIL_LIMIT` | 10 per 300 s | Wrong `/reports` codes per IP before a lockout |

## 5. Tests

```bash
.venv/bin/python -m pytest -q      # needs ./scripts/dev_db.sh running
```

The suite covers scoring, live games (SSE and concurrency), homework, teacher quizzes, the teacher-presents modes and reports.
Test data is tagged (`[pytest…]`) and removed afterwards. The tests set their own `REPORTS_KEY` (`tests/conftest.py`).

## 6. Project layout

```
app/                 FastAPI backend (Python)
  main.py            app, page routes, /api/health, routers
  live.py            live PIN games: create/join/state/SSE/answer/leaderboard/CSV
  live_self_paced.py homework (self-paced) rules
  quiz.py            teacher-owned quizzes (edit key)
  classroom.py       teacher-presents mode (individuals / groups)
  reports.py         /api/reports (program team)
  scoring.py         pure scoring functions (multiple choice, streak, points)
db/                  idempotent SQL migrations + seed content (apply in filename order)
static/              HTML/CSS/JS, no build step
  theme-se.css       ALL colours / brand values (Solve Education palette) + the shared base rules
  icons.svg          Lucide icon sprite (regenerate: node scripts/build_icons.mjs)
  brand/             Solve Education logo + GAIN mascots
scripts/             dev_db.sh, run.sh, build_icons.mjs
tests/               pytest suites
docs/                guides (this file, EC2 deploy, teacher guide, content guide, porting plan)
CONTRACT.md          API + rules (single source of truth)
```

## 7. Other guides

- [`TEACHER-GUIDE.md`](TEACHER-GUIDE.md): how to run a session (English + Bahasa Melayu)
- [`CONTENT-GUIDE.md`](CONTENT-GUIDE.md): writing good quiz questions
- [`DEPLOY-EC2.md`](DEPLOY-EC2.md): production-like setup on AWS EC2
- [`MONOREPO-PORTING.md`](MONOREPO-PORTING.md): plan for moving this into the solveeducation monorepo stack
