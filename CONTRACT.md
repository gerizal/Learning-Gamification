# CONTRACT — PlayClass quiz MVP (started as the "Speaking Game Prototype") — SSOT for all agents

> **Read "FINAL CLEAN-UP" first.** Everything below it is kept as history; sections marked **REMOVED** describe
> code that no longer exists, and the clean-up block wins wherever the two differ.

## FINAL CLEAN-UP (owner, 2026-09-28) — current truth, SUPERSEDES the sections below where they differ
Owner decisions: **the MVP is a quiz only** (multiple_choice, incl. true/false), **speaking is NOT in it**, **the admin
page is retired**, **`/practice` goes away**. The project moves into the solveeducation monorepo at `apps/game-console/`.

**Removed** (code, routes and tests): the `/practice` page (individual speaking game) and the `/admin` page;
`/api/users*`, `/api/games`, `/api/sessions*`, `/api/attempts`, `/api/leaderboard` (practice leaderboard) and every
`/api/admin/*` route (questions, stats, preview-score, packs) with the `X-Admin-Token` / `ADMIN_TOKEN` code;
`app/stt.py`, Vosk (`requirements.txt`), `scripts/download_model.sh`, every `VOSK_*` setting; `static/index.html`,
`game.js`, `recorder.js`, `feedback.js`, `admin.html`, `admin.js` and `style.css` (the rules the remaining pages use
were moved, in their original order, into **`theme-se.css` Part 1**, scoped away from `/reports`). The speaking
scorers (alignment, keywords, `score_answer`, `normalize`, …) and the practice helpers (`level_info`,
`question_streak`, `awarded_points`, `round_rank`, `mask_email`) were deleted from `app/scoring.py`.
**Kept in the DB, unchanged:** every migration in `db/` (history, idempotent) — incl. the practice tables (`users`,
`game_session`, `session_question`, `attempt`), which nothing reads any more, and `db/002_seed.sql`'s demo users and
speaking questions, which are never selected.

**Layout now:** `app/main.py` (pages `/`, `/host`, `/play`, `/classroom`, `/reports`, `GET /api/health` →
`{ok, db}`, routers), `app/live.py` + `app/live_self_paced.py` (`/api/live`), `app/quiz.py` (`/api/live/quizzes`),
`app/classroom.py` (`/api/class`), `app/reports.py` (`/api/reports`), `app/scoring.py`, `app/db.py`;
`static/` = `home.html`, `host.*`, `play.*`, `classroom.*`, `reports.*`, `live-common.js`, `i18n.js`,
`a11y-prefs.js`, `theme-se.css`, `live.css`, `icons.svg`, `brand/`. Env: `DATABASE_URL`, **`REPORTS_KEY` (required,
no default)**, plus the optional `LIVE_*` / `QUIZ_*` / `REPORTS_FAIL_*` limits (docs/SETUP.md).

**Quiz only — API rules (live, homework and classroom):**
- Question selection (`POST /api/live/games` live + self_paced, `POST /api/class/sessions`) only ever picks
  playable `multiple_choice` questions (2–4 options, valid `correct_option`). `game_modes` may be omitted or
  `["multiple_choice"]`; any other mode → **422 "game_modes: speaking questions are not supported (only
  'multiple_choice')"**. A pack whose only questions are legacy speaking rows has nothing playable → 422 "Not enough
  questions".
- Audio is never accepted: a multipart upload with a file on `POST /api/live/games/{pin}/answer`, or an `audio`
  field on `POST /api/class/sessions/{id}/turns/{n}/attempts` → **422 "speaking questions are not supported"**.
  A legacy speaking question inside an existing game / turn → the same 422 (the teacher skips it).
- Live / homework answer = JSON (or form) `{choice, idx?}` → `{accepted: true, result, …}` — the `no_speech` and
  `transcript` fields are gone. Stored `transcript` is `""`.
- Classroom turn = ONE tap (`choice`): a second attempt → 409 "one attempt for quiz"; `turn.attempts_left` is 0
  after it; the attempt's `transcript` is always `""`. The "2 attempts per turn / best-of-2" rules below are REMOVED.
- `question_counts` (on `/api/live/packs` and `/api/class/packs`) = `{"multiple_choice": n}` (playable only).
- In question views `target_text` is always `null` (kept in the shape); `reveal.correct` of a legacy speaking
  question is `{option: null, option_text: null}`. Stored `feedback.stt_words` of old answers is still stripped.
- Scoring kept in `app/scoring.py`: `score_multiple_choice`, `is_passed`, `stars_for`, `next_streak`,
  `streak_multiplier`, `base_for`, `compute_points` (classroom; the `min_bonus_accuracy` option went with
  /practice), `live_speed_factor`, `live_points`, `MULTIPLE_CHOICE`, `LIVE_GRACE_SEC`.

**Reports access (supersedes "REPORTS › Access" below):** `REPORTS_KEY` is **required**; there is no default in
code. Unset or blank → every `/api/reports/*` call answers **503 `{"detail": "reports not configured"}`** (before
any key check, so nothing counts as a failed attempt) and a WARNING is logged at startup. `GET /api/reports/status`
needs no key: 503 as above, or 200 `{"configured": true}`; `/reports` probes it on load and, when not configured,
shows "Reports are not set up on this server yet (REPORTS_KEY is missing)…" and disables the form. For local dev only,
`scripts/run.sh` exports `REPORTS_KEY="${REPORTS_KEY:-reports123}"` (DEV-ONLY comment); tests set their own key
(`tests/conftest.py`).

---

> **Product direction (owner, 2026-09-28):** this is a general Kahoot-style classroom quiz platform (see README.md), NOT a speaking game.
> Primary = LIVE GAME (bottom section) with `multiple_choice` (incl. true/false) as the default type. Speaking modes are optional extras.
> Individual speaking mode below = `/practice` (secondary).
> **No admin page** (owner): the only gate is Teacher / Student. Teachers create/edit/delete/reorder their own quizzes inside `/host` (edit-key per quiz). `/api/admin/*` is deprecated. **English is the primary language**; BM / ID are optional switcher languages. Speaking is NOT in the MVP.


Standalone project. Own PostgreSQL database (`playclass`). NO AI/cloud service:
speech-to-text = **Vosk** (offline, free, Python), scoring = pure Python (`difflib`).

## Stack / layout — SUPERSEDED 2026-09-28 (see FINAL CLEAN-UP › Layout)
```
app/            FastAPI backend (Python 3.11)
  main.py       app + routes, serves /static and / -> static/index.html, /admin -> static/admin.html
  db.py         psycopg (v3) pool, DATABASE_URL env
  stt.py        Vosk wrapper: transcribe(wav_bytes) -> {text, words:[{word, conf}]}
  scoring.py    pure functions (no I/O), unit-tested
db/001_schema.sql   schema (already written — do not change without updating this file)
db/002_seed.sql     demo users + sample questions
static/         plain HTML/CSS/JS, no build step, no framework
  index.html, game.js, recorder.js, style.css   (learner game)
  admin.html, admin.js                          (question setup / back office; reuses style.css)
scripts/        download_model.sh, dev_db.sh, run.sh
tests/          pytest
```
Env: `DATABASE_URL` (default `postgresql://localhost:5432/playclass`), `VOSK_MODEL_PATH`
(default `models/vosk-model-small-en-us-0.15`), `ADMIN_TOKEN` (default `admin123`, prototype only).

## Game modes (`game_mode`) — REMOVED 2026-09-28 (speaking modes; only `multiple_choice` remains)
| mode | Nama (UI) | Player sees | Question needs | Scored by |
|---|---|---|---|---|
| `read_aloud` | Baca Nyaring | `target_text` | `target_text` | word alignment |
| `repeat_after_me` | Tirukan Aku | play button (browser `speechSynthesis` reads `target_text`), text hidden until result | `target_text` | word alignment |
| `picture_talk` | Ceritakan Gambar | `image_url` (or big emoji in `prompt`) + `prompt` | `keywords` ≥1 | keyword hits |
| `quick_answer` | Jawab Cepat | `prompt` (a question) + countdown | `keywords` ≥1 (= accepted answers) | any accepted answer |

## Scoring rules (app/scoring.py) — speaking parts REMOVED 2026-09-28 (normalize / alignment / keywords / quick_answer / level); pass, stars, base, streak, speed bonus and points still apply
- normalize: lowercase, strip punctuation except `'`, collapse spaces, split to words.
- **alignment** (read_aloud, repeat_after_me): `difflib.SequenceMatcher(autojunk=False)` over word lists.
  equal → `correct` (1.0) — but if Vosk conf < 0.5 → `unclear` (0.8);
  replace pairs with char similarity ≥ 0.75 → `close` (0.5); otherwise `missed` (0).
  Spoken words not in target → `extra_words`. `accuracy = 100 * sum(credit)/len(target)`.
- **keywords** (picture_talk): keyword hit if phrase is in normalized transcript, or (single word) any spoken
  word with similarity ≥ 0.8. `accuracy = 100 * hits/len(keywords)`.
- **quick_answer**: accuracy = 100 if any accepted answer hit, else 0.
- `passed = accuracy >= 60`. stars: ≥90→3, ≥75→2, ≥60→1, else 0.
- `base = base_points * {1:1.0, 2:1.5, 3:2.0}[difficulty]`; `earned = round(base * accuracy/100)`.
- streak = consecutive passed attempts in the session including this one (0 if failed).
  `streak_multiplier = 1 + 0.1 * min(max(streak-1,0), 5)` (max 1.5x).
- `speed_bonus = round(base*0.1)` if passed and `duration_ms <= time_limit_sec*1000*0.5`, else 0.
- `points = round(earned * streak_multiplier) + speed_bonus` (failed → just `earned`).
- level = `1 + total_points // 500`; `level_progress = (total_points % 500)/500`.

## API (JSON unless noted; errors → `{"detail": "..."}` with 4xx) — REMOVED 2026-09-28 (practice + admin API; only the error shape and `/api/health` → `{ok, db}` remain)
- `GET /api/health` → `{ok, db, stt_model_loaded}`
- `GET /api/users?q=` → `[{id, name, email, avatar}]` (ILIKE name/email, limit 20)
- `POST /api/users` `{name, email}` → user (upsert by email)
- `GET /api/users/{id}/profile` → `{user, total_points, level, level_progress, next_level_points, sessions_played, best_streak, recent:[{game_mode, prompt, accuracy, points, stars, created_at}]}`
- `GET /api/games` → `[{mode, title, description, icon, question_count}]` (active questions only)
- `POST /api/sessions` `{user_id, game_mode, count?=5}` → `{session_id, game_mode, questions:[Question public view]}`
  Public view: `id, game_mode, prompt, target_text, image_url, difficulty, base_points, time_limit_sec` —
  **never `keywords`**. For `repeat_after_me` target_text IS sent (TTS needs it); UI hides it.
- `POST /api/attempts` **multipart**: `session_id`, `question_id`, `duration_ms`, `audio` (WAV, 16-bit PCM mono, any sample rate)
  → `{attempt_id, transcript, accuracy, passed, stars, points, streak, streak_multiplier, speed_bonus, session_total,
      feedback: {words:[{word, status}], extra_words:[...], keywords:[{keyword, hit}]}}`
  (`words` empty for keyword modes, `keywords` empty for alignment modes; keywords revealed AFTER answering is fine)
- `POST /api/sessions/{id}/finish` → `{session_id, total_points, attempts, avg_accuracy, stars_total, profile}` (profile as above)
- `GET /api/leaderboard?limit=10` → `[{rank, user_id, name, avatar, total_points, level}]`
- Admin — header `X-Admin-Token` required (401 otherwise):
  - `GET /api/admin/questions?mode=&include_inactive=true` → `[Question full]` (ordered by game_mode, sort_order, id)
  - `POST /api/admin/questions` Question input → Question full (201)
  - `PUT /api/admin/questions/{id}` Question input → Question full
  - `PATCH /api/admin/questions/{id}/active` `{is_active}` → Question full  (no hard delete — archive)
  - `GET /api/admin/stats` → `[{question_id, prompt, game_mode, attempts, avg_accuracy, pass_rate}]`
  - `POST /api/admin/preview-score` `{game_mode, target_text?, keywords?, transcript}` → scoring result
    (lets admin test a question by typing what a learner might say, no audio)
- Question input: `game_mode, prompt, target_text?, keywords: string[], image_url?, difficulty 1-3, base_points (10-1000), time_limit_sec (5-120), is_active, sort_order`.
  Validation (422): alignment modes need non-empty `target_text`; keyword modes need ≥1 keyword.

## Implementation notes (as built) — REMOVED 2026-09-28 (practice + admin API)
- 422 body: `{"detail": "<string>", "errors": [...]}` (`errors` = pydantic list, optional).
- Other codes: unknown user/session/question → 404; mode with no active questions on `POST /api/sessions` → 404;
  finished session → 409; audio > 10 MB → 413; STT model missing → 503.
- `/api/admin/stats`: `avg_accuracy` and `pass_rate` are both 0–100.
- `preview-score` returns `{transcript, accuracy, passed, stars, feedback}` — no points (admin UI computes base × accuracy for display).
- Session questions are returned in random order; `count` 1–20. Leaderboard includes 0-point users.

---
# CLASSROOM MODE ("Mode Kelas") — added after ClickUp requirement "Program Requirements for Game Console"
Context: one laptop + projector + one mic in a classroom/community centre; students have NO phones
(Malaysia). The teacher is the **game master**. Participation must be countable (program KPIs:
Lenovo Malaysia, Apptitude). Content: `ai` packs (Apptitude — strictly AI topics) and `general` packs (Lenovo).
Train-the-trainer: a first-time teacher must be able to run a session without our team.
Individual mode (above) stays unchanged. Schema: `db/003_classroom.sql` (locked).

## Rules
- Teams: 2–6, auto-named from a fixed fun list (e.g. 🐯 Harimau/Tigers, 🦅 Helang/Eagles, 🐬 Lumba-lumba/Dolphins,
  🦊 Rubah/Foxes, 🐘 Gajah/Elephants, 🦜 Kakak Tua/Parrots) with colors cyan/pink/lime/amber/violet/orange.
  Present students are shuffled and dealt round-robin into teams.
- Queue: `rounds` (1–10, default 3) × teams turns, round-robin by team position; each turn gets a random active
  question from the selected pack + modes, no repeats within the session while available.
- Speaker per turn: server SUGGESTS the team member (present) with the fewest turns so far (ties: random);
  teacher may override with any present member of that team.
- Scoring per attempt: same `app/scoring.py` rules; team streak replaces session streak (consecutive passed turns
  of THAT team; a skip or fail resets it). Max **2 attempts per turn**; turn's `best_points` = max of attempts;
  team.score = sum of best_points (recomputed, never double-counted). No speed bonus pressure: speed bonus still
  applies, but the timer in classroom mode is shown and can be paused by the teacher (client-side).
- Skip: turn → `skipped`, 0 points, team streak reset (for shy students — no shame UI).
- Participation: present = attendance.present; spoke = student has ≥1 class_attempt in the session.
  participation_rate = spoke / present.

## API (prefix /api/class)
- `GET /packs` → `[{id, slug, name, topic, description, why_it_matters, question_counts: {mode: n}}]`
- `GET /classrooms` → `[{id, name, school, teacher_name, program, student_count, last_session_at}]`
- `POST /classrooms` `{name, school?, teacher_name?, program?}` → classroom
- `GET /classrooms/{id}` → `{...classroom, students:[{id, name, is_active}]}`
- `POST /classrooms/{id}/students` `{names: string[]}` (bulk paste, trims, dedupes, ignores blanks; existing names skipped)
  → `{added:[student], skipped:[name]}`
- `PATCH /students/{id}` `{name?, is_active?}` → student
- `POST /sessions` `{classroom_id, pack_id?, game_modes: string[≥1], team_count 2–6, rounds 1–10, present_student_ids: int[≥team_count]}`
  → SessionState (201). 422 if not enough questions / students.
- `GET /sessions/{id}` → **SessionState**:
  `{id, status, classroom:{id,name}, pack:{id,name,topic}|null, game_modes, current_turn, total_turns,
    teams:[{id, name, emoji, color, position, score, streak, members:[{student_id, name, turns_spoken}]}],
    turns:[{turn_no, team_id, status, student_id, best_points, question:{public view as individual mode}}],
    next:{turn_no, team_id, suggested_student_id} | null,
    participation:{present, spoke, rate}}`
- `PUT /sessions/{id}/teams` `{teams:[{team_id, student_ids}]}` → SessionState (only before any attempt; 409 after)
- `POST /sessions/{id}/turns/{turn_no}/attempts` multipart `student_id, duration_ms, audio(WAV)` →
  `{attempt_no, transcript, accuracy, passed, stars, points, streak, streak_multiplier, speed_bonus, feedback,
    turn:{turn_no, status, best_points, attempts_left}, team:{id, score, streak}, state: SessionState}`
  409 if session finished, turn not current, or 2 attempts used; 422 if student not a present member of the turn's team.
- `POST /sessions/{id}/turns/{turn_no}/next` `{}` → marks current done (if attempted) and advances → SessionState
- `POST /sessions/{id}/turns/{turn_no}/skip` `{student_id?}` → SessionState
- `POST /sessions/{id}/finish` → `{state: SessionState, ranking:[{team_id, name, emoji, score, rank}],
    mvp:{student_id, name, team_id, points}|null,
    participation:{present, spoke, rate, students:[{student_id, name, team, present, turns, attempts, best_accuracy, points}]}}`
- `GET /sessions/{id}/participation.csv` → CSV (school, classroom, program, date, student, team, present, spoke, turns, points, avg_accuracy)
- `GET /reports/participation?program=&from=&to=` → `{sessions, classrooms, unique_students_present, unique_students_spoke,
    by_classroom:[{classroom_id, name, school, program, sessions, present, spoke}]}`  (program KPI counting)
- Admin (`X-Admin-Token`): question input/output gains optional `pack_id`; `GET /api/admin/packs`, `POST /api/admin/packs`, `PUT /api/admin/packs/{id}`.

## UI (`/classroom`, files static/classroom.html, classroom.js, classroom.css — reuse style.css tokens + `.theme-console`; since 2026-09-28 those base rules live in theme-se.css Part 1)
Projector-first (1280×720 and 1920×1080, readable from the back of the class: question text ≥ 48px),
teacher-operated with mouse/keyboard; also OK on a tablet. Languages: EN / BM (Bahasa Melayu) / ID switcher
(teacher UI strings; learning content stays English).

## Classroom — Implementation notes (as built, backend)
- Code: `app/classroom.py` (`router` = /api/class, `admin_router` = /api/admin/packs, mounted with the admin-token
  dependency). Page route `GET /classroom` → static/classroom.html (404 until the file exists).
- Status codes: `POST /classrooms` → 201, `POST /sessions` → 201, `POST /api/admin/packs` → 201; everything else 200.
  Unknown classroom/student/session/turn/pack → 404. Duplicate pack slug / duplicate student name on PATCH → 409.
  Archived pack on `POST /sessions` → 422. Unknown `pack_id` on admin question create/update → 422.
- Classroom object: `{id, name, school, teacher_name, program, created_at, student_count, last_session_at}`
  (`student_count` = active students). `GET /classrooms` ordered by name.
- Students bulk add: names trimmed and inner whitespace collapsed; dedupe and "existing" checks are
  **case-insensitive**; in-paste duplicates are dropped silently, names already in the class (or > 100 chars)
  go to `skipped`. Response 200.
- `GET /packs` lists active packs only; `question_counts` always has all 4 modes (active questions). Admin pack
  object = `{id, slug, name, topic, description, why_it_matters, is_active, created_at, question_counts}`;
  slug must match `^[a-z0-9]+(-[a-z0-9]+)*$`; PUT is a full replace; no delete (archive with `is_active=false`).
- Admin questions: `pack_id` is in Question full. On **PUT, omitting `pack_id` keeps the current pack** (so the
  older admin form can't silently unassign pack questions); send `"pack_id": null` to clear.
  `GET /api/admin/questions` also accepts `?pack_id=`.
- `POST /sessions`: `pack_id` null/omitted = all active questions of the chosen modes (any pack or none).
  Duplicate ids in `game_modes` / `present_student_ids` are de-duplicated before the ≥ team_count check.
  Every present id must be an **active** student of that classroom (422). Attendance rows are written for all
  active students of the classroom (`present=false` for the ones not listed). 422 "not enough questions" only
  when zero questions match; with fewer questions than turns the pool is reshuffled after it is used up.
- Team name = `"<BM> / <EN>"` e.g. `"Harimau / Tigers"`, emoji separate; positions are 1-based and team *i*
  always gets list entry *i* (fixed order, so colors are cyan, pink, lime, ...).
- SessionState extras (additive): `started_at`, `finished_at`, and `turns[].attempts_used` (so a reloaded UI knows
  how many attempts are left). `next` is null when the session is finished or all turns are resolved
  (`current_turn` then = total_turns + 1; the session stays `live` until `finish`). `participation.rate` is a
  0–1 fraction (4 decimals).
- `turns_spoken` = distinct turns where the student attempted **or** was named on a skip. Suggestion = fewest
  `turns_spoken` among the team's members, ties broken randomly but **seeded by session+turn**, so repeated GETs
  return the same suggestion; once someone has attempted the current turn the suggestion stays on them.
- Team streak: streak for an attempt = (consecutive passed turns of that team *before* this turn) + 1 if passed,
  else 0; both attempts of a turn share that base. A turn counts as passed if any attempt passed.
  `team.score` = SUM(best_points) and `team.streak` are recomputed from history after every attempt/next/skip.
  `class_turn.student_id` = the student of the best attempt (ties: earliest).
- `next` on a turn with no attempt marks it `skipped` (0 points, streak reset); with attempts → `done`.
  `skip` on a turn that already has an attempt → **409** (use `next` to keep its points). `skip`'s `student_id`
  (optional) must be a present member of the turn's team (422). next/skip/attempt on a turn that is not current,
  or on a finished session → 409 (so a double-clicked "next" advances only once).
- Attempt error order: 404 session/turn → 409 finished / not current / 2 attempts used → 422 student not a present
  member → 413/422 audio → 503 STT. Checked once before STT and again under the row lock.
- Concurrency: attempt/next/skip/teams/finish take `SELECT … FOR UPDATE` on `class_session` (and the `class_turn`
  row); the DB part runs in the threadpool, so concurrent requests really serialise. `attempt_no` = count+1
  under the lock. Session creation and team edits are single transactions.
- `PUT /sessions/{id}/teams`: must list every team exactly once, each with ≥ 1 student, covering exactly the
  present students with no duplicates (422 otherwise); 409 after the first attempt or when finished.
- `POST /finish` is idempotent (keeps the first `finished_at`); unplayed turns stay `pending`. Ranking is by
  score (ties share a rank: 1, 1, 3). Student `points` = SUM(best_points) of turns credited to them; MVP = most
  points (> 0), ties → higher best_accuracy, then name; null if nobody scored. `participation.students` lists
  every attendance row (absent students have `team: null`, `present: false`); `best_accuracy` null if no attempt.
- CSV: UTF-8 with BOM (Excel), CRLF, one row per attendance row; `present`/`spoke` = `yes`/`no`; `date` = session
  start date; `team` empty for absent; `avg_accuracy` empty if no attempts; filename
  `participation-<date>-<session_id>.csv`.
- Reports: `program` matches case-insensitively (exact, trimmed); `from`/`to` are inclusive dates (YYYY-MM-DD)
  on the session start date in the DB timezone; all sessions count (live or finished). `present`/`spoke` in
  `by_classroom` are unique students across that classroom's matching sessions.

---
# LIVE GAME (Kahoot-style) — PRIMARY EXPERIENCE (owner decision 2026-09-28)
Owner: "sesimple mungkin… halaman pertama I am Teacher / I am Student, terus ada code, ga usah dashboard… kaya Kahoot".
See README.md (product brief). Schema: `db/006_live.sql` (locked).

## Pages
- `/` → `static/home.html`: brand, two huge buttons **I'm a Teacher** / **I'm a Student**, and a big
  "Game PIN" input + Join (a `?pin=` link pre-fills). Nothing else. EN / BM toggle (ID optional).
- `/host` → `static/host.html` (teacher, laptop + projector). Flow:
  1. Create: title (optional), pick a pack (cards: AI / General, with "Why teach this?" expandable), pick
     question types (default all), number of questions (5/10/15), optional teacher/school/program → **Create game**.
     A secondary link: "No student devices? Play on one screen (teams)" → `/classroom`.
  2. Lobby: giant PIN + join URL + QR-free (text) instructions, live list of joined nicknames (teacher can kick/rename),
     player count, **Start**.
  3. Question: question shown huge, countdown, "N / M answered", Skip-timer button. Speaking questions: students
     speak into THEIR device; host shows only the prompt (repeat_after_me: host plays TTS for the whole room).
  4. Reveal: correct answer / target sentence, accuracy distribution (e.g. 3 bars: great / ok / try again),
     top 3 of this question.
  5. Leaderboard: top 5 with rank changes, **Next**.
  6. Podium (top 3) + "N students joined · M answered at least once" + Download CSV + New game.
- `/play` → `static/play.html` (student phone/tablet/PC): enter PIN → nickname → "You're in! Look at the screen"
  → per question: the prompt (also shown on device), big mic button (record → preview → re-record allowed → Submit;
  one submission per question) or 4 coloured option tiles for multiple_choice → "Answer sent" → result
  (correct/stars/points/rank) → wait → final rank. Survives refresh (player_token in localStorage).
- `/practice` → old individual game (static/index.html), `/classroom` one-screen team mode, `/admin` question setup.
  None of these are linked from `/` except via the teacher page's small links.

## Rules
- PIN: 6 random digits, unique among non-ended games. host_token / player_token: 32-byte urlsafe secrets.
- Question queue: N random active questions from pack + selected types (no repeats), fixed at create.
- Phases driven ONLY by the host: lobby → question → reveal → leaderboard → question … → ended.
  Answers accepted only in `question` phase for the current idx; one per player (UNIQUE) — 409 otherwise.
  Server auto-accepts until time_limit_sec + 3 s grace after phase_started_at; later → 409.
- Scoring: speaking modes use app/scoring.py accuracy/passed/stars. multiple_choice: accuracy 100 if correct else 0.
  Kahoot-style speed factor on SERVER time: `points = round(base * accuracy/100 * (1 - 0.5 * answer_ms / (time_limit_sec*1000)))`
  if passed else 0; `base = base_points * difficulty multiplier`. Streak (consecutive passed questions) bonus
  +10% per streak step, max +50%. Empty transcript → "no speech" (0 points, no streak reset, player may re-record
  and submit again before time is up — the no-speech submission is NOT stored).
- Player sees own result only after host moves to `reveal` (keeps suspense, like Kahoot).

## Realtime
- `GET /api/live/games/{pin}/events` — **Server-Sent Events**. Event `state` with the role-appropriate state on
  every change (host token via `?host_token=`, player via `?player_token=`). Fan-out uses Postgres
  `LISTEN/NOTIFY` (channel `live_<game uuid without dashes>`) so the API stays stateless / multi-instance safe
  (Redis can replace it later). Clients fall back to polling `GET …/state` every 2 s if SSE fails.
- Heartbeat comment every 15 s.

## API (prefix /api/live)
- `POST /games` `{pack_id?, game_modes[], question_count 1–30, title?, teacher_name?, school?, program?}` →
  `{game_id, pin, host_token, join_url}` (201); 422 if not enough questions.
- `GET /games/{pin}/state?host_token=|player_token=` → **LiveState**:
  `{pin, status, title, index, total, phase_started_at, server_now,
    question: {idx, game_mode, prompt, target_text?, image_url, image_alt, options?, time_limit_sec} | null,
    players_count, answered_count,
    // host only:
    players:[{id, nickname, score}],
    reveal: {correct: {target_text|keywords|option}, distribution:{great, ok, retry, no_answer}, top:[{nickname, points}]} | null,
    leaderboard:[{rank, nickname, score, delta_rank}] (in leaderboard/ended),
    // player only:
    me: {id, nickname, score, rank, answered_current, last_result: {accuracy, passed, stars, points, transcript, feedback} | null (only from reveal on)}}`
  Keywords / correct option are never sent to players before `reveal`.
- `POST /games/{pin}/join` `{nickname}` → `{player_id, player_token}` (201). 1–20 chars, trimmed, unique per game
  (409 "name taken"), 404 unknown PIN, 409 if status = ended. Late join (after start) is ALLOWED; the player starts at 0.
  Simple rate limit: 10 joins / 10 s per IP → 429.
- Host actions (`X-Host-Token` header; 403 otherwise): `POST /games/{pin}/start`, `/next` (question→reveal→leaderboard→next question… last leaderboard→ended),
  `/end`, `POST /games/{pin}/players/{id}/kick`, `PATCH /games/{pin}/players/{id}` `{nickname}`.
- `POST /games/{pin}/answer` (`X-Player-Token`): multipart `audio` (speaking) or JSON/form `choice` (multiple_choice)
  → `{accepted: true, no_speech: bool}` (result revealed later via state).
- `GET /games/{pin}/report.csv?host_token=` → per player: nickname, answered, correct, avg_accuracy, score, rank, + game meta.
- Admin: question input gains `options: string[]` (2–4) + `correct_option` (0-based) required for multiple_choice;
  `options` ignored for other modes.

---
# CHANGES AFTER REVIEW (individual mode `/practice` + admin) — reviews/a11y-review.md, reviews/ux-review.md — REMOVED 2026-09-28
Schema: `db/005_review_fixes.sql` (idempotent): `question.image_alt text`, table `session_question(session_id,
question_id, position)` (what a session served), `attempt.awarded_points int` (NULL on older rows → readers use
`COALESCE(awarded_points, points)`). Details and evidence: `reviews/fix-log.md`. Classroom mode is unchanged.

## Individual-mode scoring (replaces the per-attempt rules above for `/api/attempts` and `/finish`)
- **Served questions only:** `POST /api/sessions` stores the served ids; `POST /api/attempts` on a question that was
  not served in that session → **422** "Question N was not served in this session" (after the 404s and the
  wrong-mode 422; before STT).
- **Streak is over questions, not attempts:** streak for an attempt = (consecutive passed questions answered before
  this one, in first-attempt order) + 1 if passed, else 0. A question counts as passed if any attempt passed. All
  attempts on one question share the same base, so a retry can neither extend nor reset the combo.
- **Best attempt counts:** `points` is still the attempt's own value; the attempt ADDS only
  `points_awarded = max(0, points − best points of earlier attempts on that question)`. `session_total`, profile
  `total_points` and the leaderboard are sums of awarded points (= sum of the best attempt per question).
- **Speed bonus** (individual only) additionally needs accuracy ≥ 90 (3★) — a cut-off short answer is not rewarded
  (`scoring.compute_points(min_bonus_accuracy=…)`, classroom passes nothing = unchanged).
- **No speech:** empty/blank transcript → **200** `{status:"no_speech", no_speech:true, attempt_id:null, points:0,
  points_awarded:0, streak:<current combo, unchanged>, session_total:<unchanged>, …}`. Nothing is stored: no
  points, no streak reset, not counted as an attempt.
- Attempt response = old fields + `status` ("scored"|"no_speech"), `no_speech`, `points_awarded`, `best_points`,
  `best_stars`, `is_best`, `question_attempts`. `streak` = the session combo after this attempt.
- `POST /api/sessions/{id}/finish` → old fields + `questions_served`, `questions_answered`, `completed`
  (= every served question has ≥1 scored attempt), `rank` ("S"|"A"|"B"|"C", **null when `completed` is false**),
  `recap:[{question_id, position, prompt, target_text, answered, best_accuracy|null, best_stars, best_points, attempts}]`.
  `avg_accuracy` = mean of the best accuracy per answered question; `stars_total` = sum of best stars per question;
  `attempts` = number of stored attempts. The UI shows "Stage Clear"/rank only when `completed`.

## Other API changes
- `GET /api/users?q=` → `[{id, name, avatar, email_masked, level}]` — **no `email`**. Needs ≥ 2 characters (else `[]`);
  matches name (ILIKE, wildcards escaped) or the exact email. `email_masked` = first letter + `***@domain`.
- Profile `user` = `{id, name, avatar, email_masked}` (no raw email). `recent` = best attempt per (session, question),
  newest first, max 10: `{game_mode, prompt, target_text, accuracy, points, stars, created_at, session_id,
  question_id, attempts}`.
- `GET /api/games` items gain `min_difficulty, max_difficulty, avg_difficulty, difficulty` (rounded avg; null when the
  mode has no active questions), computed from active questions.
- `GET /api/leaderboard`: players with 0 points are not listed.
- Question public view and full view gain `image_alt` (≤ 300 chars, blank → null). **On PUT, omitting `image_alt`
  keeps the current value** (same rule as `pack_id`). picture_talk UI alt text: `image_alt`, else a text
  description of the prompt — never a generic "Gambar soal".
- Keywords: `|`, `;` and `,` inside a keyword item (or string) are separators (`["elephant;tree"]` → 2 keywords).
- Admin `GET /api/admin/questions` and `/api/admin/stats` are ordered in learner mode order
  (read_aloud, repeat_after_me, picture_talk, quick_answer), then sort_order, id.
- `GET /api/admin/stats` items: `question_id, prompt, target_text, game_mode, attempts` (all attempts), `plays`
  ((session, question) pairs), `players`, `avg_accuracy` and `pass_rate` (0–100, over the best attempt of each play),
  `missed_words:[{word, count}]` (top 5 non-correct target words).

## Shared front-end modules (reusable by /play, /host) — `feedback.js` REMOVED 2026-09-28; `a11y-prefs.js` now only reads a stored reduce-motion choice + the OS setting (`reduceMotion()`, `applyPrefs()`)
- `static/a11y-prefs.js` — learner preferences in localStorage: `reduceMotion` (OS setting OR in-app
  "Kurangi animasi"; sets `html[data-motion="reduce"]`), `timer` ("normal" | "long" = 2× | "off"),
  `showRepeatText` (Tirukan Aku shows the sentence), `hideLeaderboard`. `timeLimitFor(sec)` → seconds or `Infinity`.
- `static/feedback.js` — `renderWordFeedback(words, {onWord})`, `renderKeywordFeedback(keywords, mode)`,
  `usefulExtraWords(extra, target)`, `speakText(text, {rate})`: status glyphs ✓ ≈ ? ✗ (not colour-only), words are
  buttons that speak themselves (speechSynthesis, offline in the browser).

---
# Live — implementation notes (as built, backend: `app/live.py`, tests `tests/test_live.py`, `tests/test_live_scoring.py`)
**Product decision (owner, 2026-09-28): this is a general Kahoot-style classroom QUIZ platform, not a speaking game.**
`multiple_choice` is the primary/default question type (true/false = multiple_choice with 2 options, no extra mode).
Speaking modes stay supported as an opt-in. Quiz content: `db/008_quiz_seed.sql` (content agent).

## Question model (admin) — `multiple_choice` — admin API REMOVED 2026-09-28 (the option rules live on in `/api/live/quizzes`)
- Question input/full view gain `options: string[]` and `correct_option: int|null` (0-based).
  multiple_choice: 2–4 options, each trimmed, non-empty, ≤ 200 chars, no case-insensitive duplicates, and
  `0 <= correct_option < len(options)` — else 422. `target_text` / `keywords` not required for it.
  Other modes: `options` / `correct_option` are ignored and stored as `[]` / null. PUT always replaces them.
- `GET /api/admin/questions?mode=multiple_choice` works; in the default ordering MC sorts after the 4 speaking modes.
- Individual mode (`/practice`) is speaking-only: `/api/games` does not list multiple_choice, `POST /api/sessions`
  with `game_mode: "multiple_choice"` → 422, `preview-score` rejects it (422).
- `app/scoring.py` (pure, additive — existing functions unchanged): `MULTIPLE_CHOICE`, `ALL_MODES` (= GAME_MODES +
  multiple_choice; GAME_MODES stays the 4 speaking modes), `LIVE_GRACE_SEC = 3`, `score_multiple_choice(choice,
  correct_option)` (same shape as `score_answer`, feedback `{words:[], extra_words:[], keywords:[], choice, correct}`),
  `live_speed_factor(answer_ms, time_limit_sec)` = `1 - 0.5*t/limit` with t clamped to [0, limit] (grace-period
  answers get 0.5), `live_points(...)` → `{points, speed_factor, streak_multiplier}`.
- A multiple_choice question is only *playable* (live game, classroom, pack counts) with 2–4 options and a valid
  correct_option (SQL guard), so a half-edited row can never be served.

## Live game — decisions
- **Points** = `round(base * accuracy/100 * speed_factor * streak_multiplier)` if passed, else 0; one rounding.
  `streak_multiplier = 1 + 0.1 * min(streak-1, 5)` (same as `scoring.streak_multiplier`: 1st pass ×1.0, max ×1.5).
  Streak = consecutive passed *answered* questions: a stored failed answer resets it to 0; **not answering (or only
  no-speech) leaves it unchanged**. `answer_ms` = DB clock (`clock_timestamp() - phase_started_at`) when the answer
  request is received, before STT, so recognition time never costs points.
- **Scores are applied when the question closes** (question → reveal, or `/end` during a question), exactly once, under
  the game row lock. Before that nobody — player or host/projector — sees points, ranks moving, or who was right
  (`me.score`, `players[].score` stay unchanged during the question). `players[].answered` (host) is visible.
- **Phases**: `/start` lobby → question 0. `/next`: question → reveal → leaderboard → next question; after the last
  question's leaderboard → ended. `/next` in lobby or ended → 409. `phase_started_at` is reset on every transition.
  `index` stays at the last question in `ended`. `/start` with 0 players is allowed.
- **Double-click protection for `/next`**: optional JSON body `{status, index}` = the phase the host UI is showing;
  a mismatch → 409 "Stale: …". **The host UI should always send it.** Without a body (or `{}`), a second `/next`
  within 700 ms of the last transition → 409 "Next pressed twice; ignored". Both paths run under
  `SELECT … FOR UPDATE` on `live_game`, so concurrent clicks really serialise. `/start` twice → 409.
- `/end` is idempotent (200 + state). Host actions return the **host LiveState**.
- **Kick**: allowed in every phase (also after end, to clean the report); idempotent. Kicked players get 403 on
  state/answer ("You were removed from this game"), their SSE stream receives `event: kicked` and closes; they vanish
  from players/leaderboard/counts/CSV. **The kicked nickname stays reserved** in that game (a troll can't rejoin as
  the same name). Unknown player id (or other game's) → 404.
- **Rename** (`PATCH`): same nickname rules as join; 409 "name taken"; 404 for a kicked/unknown player; any phase.
- **Nickname**: control chars removed, whitespace collapsed + trimmed, 1–20 chars (422), unique per game
  **case-insensitively** (409 "name taken").
- **Join** → 201 `{player_id, player_token, nickname (normalised), game_id}`. Error order: 429 rate limit (checked
  first, it guards PIN guessing) → 422 nickname → 404 unknown/malformed PIN → 409 ended / name taken.
- **PIN** lookup: 6 digits (malformed → 404). Several ended games may share a PIN; the live game wins for join / public
  lookup; host and player endpoints find *their* game by comparing the token against every game with that PIN
  (so an old game's CSV stays downloadable after the PIN is reused). PIN range 100000–999999.
- **Tokens**: `secrets.token_urlsafe(32)`, compared with `secrets.compare_digest` (never `WHERE token = …`).
  Host token: header `X-Host-Token` on actions; `?host_token=` (or the header) on state / events / report.
  Player token: header `X-Player-Token` on answer; `?player_token=` (or header) on state / events.
  No token / wrong token → 403; unknown PIN → 404 (checked first). No state ever contains a token.
- **Answer** `POST /games/{pin}/answer`: JSON `{choice, idx?}`, or multipart/urlencoded `choice` / `audio` + `idx?`.
  `idx` (optional, recommended) = the question the client is answering; mismatch → 409 (a slow upload can't land on the
  next question). Error order: 404 → 403 (bad token / kicked) → 409 (not `question` phase / wrong idx / time up
  after `time_limit_sec + 3 s` / already answered) → 422 (choice missing or out of range for MC; audio missing for a
  speaking question; bad WAV) → 413 (> 10 MB) → 503 (STT model). Re-checked under lock after STT (FOR SHARE on
  live_game, FOR UPDATE on live_player, UNIQUE(game_id, idx, player_id) → 409 "Already answered").
  Responses: MC / speech `{accepted: true, no_speech: false}` (+ `transcript` for speech);
  **no speech** (blank transcript) → **200 `{accepted: false, no_speech: true}`**, nothing stored, no streak change,
  the player may record again until the deadline. Answers for speaking modes store Vosk words in feedback
  (`stt_words`), which is stripped from every state.
- **LiveState** (additive to the contract shape): `game_id`, `time_left_ms` (server-computed, question phase only,
  else null), `question.{difficulty, base_points}`; `question.target_text` only for read_aloud / repeat_after_me
  (null otherwise), `question.options` only for multiple_choice (null otherwise); `question` is null in lobby/ended.
  - host: `players:[{id, nickname, score, rank, answered, joined_at}]`,
    `reveal` (reveal + leaderboard phases, else null) = `{correct, distribution:{great, ok, retry, no_answer,
    options?:[count per option] (MC)}, top:[{nickname, points}] (≤3, points > 0, faster first on ties),
    answers:[{player_id, nickname, accuracy, passed, stars, points, transcript, choice, answer_ms, streak,
    speed_factor, streak_multiplier}]}`; `correct` = `{option, option_text}` (MC) | `{target_text}` (read_aloud,
    repeat_after_me) | `{keywords}` (picture_talk, quick_answer). great = 3★ (MC correct), ok = passed < 3★,
    retry = stored failed answer, no_answer = active players without a stored answer.
    `leaderboard` (leaderboard + ended, else null) = all active players `[{rank, player_id, nickname, score,
    delta_rank}]` sorted by score desc, nickname; ranks are shared on ties (1, 1, 3); `delta_rank` = previous rank −
    new rank (positive = moved up), always 0 after the first question. `summary: {joined, answered_any}` (always).
  - player: `me: {id, nickname, score, rank, streak, answered_current, last_result}`; `last_result` (reveal /
    leaderboard / ended, for the current/last question, null if not answered) = `{accuracy, passed, stars, points,
    transcript, choice, answer_ms, streak, speed_factor, streak_multiplier, feedback}`. Players also get
    `reveal: {correct}` from reveal on (never distribution/answers) and `leaderboard` = top 5
    `[{rank, nickname, score, delta_rank}]` in leaderboard/ended. No `players`, no `summary`, no ids of others.
- **`GET /api/live/packs`** (new): active packs with `question_counts` for all 5 modes (playable questions only) —
  for the host's create screen. **`GET /api/live/games/{pin}`** (new, public, rate limited 30/10 s/IP):
  `{pin, title, status, joinable}` for the join screen's PIN check.
- **Create** (`POST /games`, 201): `game_modes` omitted → `["multiple_choice"]`; `[]` / unknown mode → 422; duplicates
  removed. `question_count` 1–30 (default 10). Fewer playable questions than requested → 422 "Not enough questions: N
  available …". Unknown pack → 404, archived pack → 422. `pack_id` null = all active questions. Title defaults to
  the pack name, else "Live quiz". Response adds `title`, `total`. `join_url` = `<request base>/play?pin=<pin>`
  (override the base with env `LIVE_PUBLIC_URL` behind a proxy).
- **CSV** (`report.csv`, any phase): UTF-8 BOM, CRLF, columns `pin, title, date, teacher_name, school, program, pack,
  questions, nickname, answered, correct, avg_accuracy, score, rank`; one row per non-kicked player ordered by rank;
  `avg_accuracy` (0–100, 2 decimals) over stored answers, empty if none; `correct` = passed answers; filename
  `live-<date>-<pin>.csv`.
- **Pages**: `/` → static/home.html (falls back to static/index.html while home.html doesn't exist), `/host`,
  `/play` (404 until the file exists), `/practice` → static/index.html.

## Realtime (as built)
- NOTIFY: `pg_notify('live_<uuid hex>', '{"game_id": "...", "v": "<pg_current_xact_id>"}')` inside the same
  transaction as every change (join, kick, rename, answer, start, next, end) → delivered only on commit.
  No-op actions (kick twice, rename to same name, end twice) don't notify.
- One listener per process/event loop (`live.Broker`): a single async psycopg connection, LISTEN/UNLISTEN per channel
  as SSE streams come and go (≤ 0.2 s to take effect; the stream waits for it before its first read), fan-out to
  per-stream asyncio queues, auto-reconnect (streams re-read after a reconnect). Works with any number of uvicorn
  workers / instances (tested: the TestClient app and a uvicorn app in one process each run their own broker).
- SSE stream: `retry: 2000`, then `event: state` + `data: <LiveState JSON>` on connect and after every NOTIFY
  (bursts are coalesced ~50 ms; a stream always delivers the *latest* state, so very fast consecutive transitions
  may arrive as one event); unchanged states (ignoring `server_now` / `time_left_ms`) are not re-sent; `id:` = the
  NOTIFY version. Heartbeat comment `: ping` every 15 s (env `LIVE_HEARTBEAT_SEC`). Disconnects are noticed within
  ~1 s and the subscription is removed (UNLISTEN when the channel has no more streams). Auth errors are plain
  HTTP 403/404 before the stream starts. Players get `event: kicked` then the stream ends. After `ended` the stream
  stays open — **clients should `close()` their EventSource on `status == "ended"`** (else it would just reconnect).
- Polling fallback: `GET …/state` (same payload).

## Scaling notes / known limits (prototype)
- **Rate limit is in-memory per process** (10 joins / 10 s / IP; env `LIVE_JOIN_LIMIT`, `LIVE_JOIN_WINDOW_SEC`).
  **Must move to Redis (INCR+EXPIRE or a token bucket) when running more than one instance.** It keys on the TCP
  peer IP (`X-Forwarded-For` is not trusted; use uvicorn `--proxy-headers` behind a trusted proxy). A whole class
  behind one school NAT shares one IP → 10 joins per 10 s for the class; raise the limit (or key on PIN+IP) for pilots.
- Each SSE stream re-reads its state from Postgres on every change (≈ 5 small queries). Fine for a few classes
  (30–40 players → ~1 k reads per question burst, coalesced). For many concurrent classes: cache the per-game
  public state in Redis and publish it once per change (Redis pub/sub can replace LISTEN/NOTIFY; channel names
  unchanged), and move per-player extras to the client.

## Classroom mode — multiple_choice turns (`app/classroom.py`)
- `POST /api/class/sessions`: `game_modes` may include `multiple_choice`; **omitted → `["multiple_choice"]`**
  (explicit `[]` still 422). Only playable MC questions are queued.
- SessionState `turns[].question` gains `options` (list for multiple_choice, null otherwise); `correct_option` is
  never sent. `question_counts` (packs) now has 5 keys (adds `multiple_choice`).
- `POST /sessions/{id}/turns/{n}/attempts`: multipart `student_id`, `duration_ms` (now optional, default 0), and
  either `audio` (speaking turn) or `choice` (0-based, quiz turn; audio ignored). Quiz scoring: correct = accuracy
  100 / passed, wrong = 0; same compute_points, best-of-turn and team streak rules. **Quiz turns allow ONE attempt**:
  a second → 409 "one attempt for quiz"; `turn.attempts_left` = 0 after it. Missing/out-of-range choice on a quiz
  turn → 422; missing audio on a speaking turn → 422 (both after the 404/409/student checks).

## Live — update 2 (owner: "better than Kahoot"; SUPERSEDES the notes above where they differ)
Migration `db/009_live_settings.sql`: `live_game.allow_rename bool DEFAULT true`, `live_game.instant_feedback bool
DEFAULT true`, `live_answer.applied bool` (points added to the player yet? pre-existing rows = true),
`live_player.renamed_at timestamptz` (self-rename cooldown, in the DB so it holds across instances).
Speaking is not in the MVP: the backend support stays, nothing new is built for it.

### Host settings
- `POST /games` accepts `allow_rename` and `instant_feedback` (both default **true**).
- `PATCH /games/{pin}/settings` `{allow_rename?, instant_feedback?}` (X-Host-Token; 403 otherwise; 422 bad types)
  → host LiveState, any phase; no-op changes don't NOTIFY. Every state carries
  `settings: {allow_rename, instant_feedback}`.

### Instant feedback (default) vs Kahoot-like — exactly once in both modes
- `instant_feedback = true`: the answer is scored at submit and added to the player's score/streak **in the same
  transaction** under the existing locks (FOR SHARE live_game + FOR UPDATE live_player), stored `applied = true`.
  Answer response = `{accepted, no_speech, result}`, `result` = the player's `last_result` (below). The player's
  state has it immediately; scores and leaderboards move live during the `question` phase.
- `instant_feedback = false`: stored `applied = false`, `result: null`; applied when the question closes
  (→ reveal, or `/end` during the question). Nothing visible before (Kahoot-like, unchanged).
- **Exactly-once rule**: pending answers are applied by ONE statement that flips `applied` false→true and adds
  exactly the flipped rows (`WITH app AS (UPDATE live_answer … RETURNING) UPDATE live_player … FROM app`), always
  under the live_game FOR UPDATE lock. Switching the setting ON mid-question applies what was stored so far;
  switching it OFF only affects later answers. Tested: 40 simultaneous answers + concurrent setting flips → every
  player's score = the points of their one answer, all rows applied.
- `me.last_result` appears as soon as the player's own answer is applied (instant: at once; deferred: from reveal)
  and adds `correct` (`{option, option_text}` MC | `{target_text}` | `{keywords}`) — only the player's OWN result.
  Players who haven't answered and the host projector (`reveal`) still see nothing before reveal.
- `answer_ms`, the points formula and the streak rules are unchanged.

### Leaderboard in every phase (REPLACES the earlier list-shaped `leaderboard`)
- Computed by one ordered window query over live_player (RANK() now + RANK() at the start of the current question);
  no per-player queries; a state costs 5 queries regardless of player count.
- Player: `leaderboard: {top: [≤10 {rank, nickname, score, delta_rank}], me: {rank, score,
  above: {nickname, score_gap} | null}}` — always (lobby too). `above` = the player just ahead in the order
  (score desc, nickname, id); `score_gap` ≥ 0 (0 on a tie).
- Host: `leaderboard: {top: [≤10 {rank, player_id, nickname, score, delta_rank}], rank_changes: [{player_id,
  nickname, from, to}]}` — always. `delta_rank` / `rank_changes` = movement since the start of the current question
  (0 / [] on the first question). The full list stays in `players` (joined order, with `rank`).

### Player self-rename
- `PATCH /games/{pin}/me` `{nickname}` (X-Player-Token) → player LiveState; any phase except `ended`.
  Error order: **422** nickname (same rules as join) → **404** PIN → **403** bad token / kicked → **409** ended →
  **403** "renaming locked by teacher" (`allow_rename = false`) → **429** (1 rename per 10 s per player, DB clock) →
  **409** "name taken" (case-insensitive; kicked names stay reserved). Same name → 200 no-op (no cooldown).
  NOTIFY on change. Answers and score stay attached to the player id. The host rename (`PATCH /players/{id}`) ignores
  `allow_rename` and the cooldown.

### SSE throttle + shared snapshots
- Per process, all streams of a game share ONE DB snapshot per change (a per-channel generation counter is bumped on
  every NOTIFY; a snapshot read started after that NOTIFY is reused by every stream wanting that generation); each
  stream renders its role's state from it. Pushes are throttled to **≤ 5 per second per stream** (≥ 200 ms apart),
  everything arriving meanwhile is coalesced. Tested: a 40-answer burst → ≤ 6 pushes in any 1-s window and far
  fewer pushes than changes. A player stream that doesn't find itself in a cached snapshot re-reads fresh once before
  concluding `kicked`.

---
# TEACHER QUIZZES (owner: NO admin page; teachers create/edit their own quizzes in the host flow)
Code `app/quiz.py` (router `/api/live/quizzes`), tests `tests/test_quiz.py`. Migration `db/010_teacher_quiz.sql`:
`question_pack.edit_key_hash`, `question_pack.owner_label` (+ unique partial index on the hash),
`classroom.is_archived`. (Before 010 is applied the quiz endpoints answer 503 and `/packs` shows `editable: false`.)
- A quiz = a `question_pack` row with an **edit key** (32-byte urlsafe secret) returned ONCE; only `sha256(key)` is
  stored; `X-Edit-Key` is checked hash-vs-hash with `secrets.compare_digest`. Unknown quiz → 404; missing/wrong key
  → 403; seeded pack (no key) → 403 "read-only; duplicate it to edit".
- `POST /api/live/quizzes` `{name 1–100, description? ≤1000, topic? 'general'|'ai' (default general),
  owner_label? ≤100}` → 201 `{pack_id, edit_key}`. Rate limit **20 / hour / IP** (shared with duplicate; in-memory,
  env `QUIZ_CREATE_LIMIT` / `QUIZ_CREATE_WINDOW_SEC`) → 429 — move to Redis when scaling.
- `POST /api/live/quizzes/{id}/duplicate` (seeded: no key; own quiz: its key) → 201 `{pack_id, edit_key,
  question_count}`: name + " (copy)", copies the active playable multiple_choice questions (sort_order 1..n).
  Unknown / archived pack → 404.
- With `X-Edit-Key`:
  - `GET /api/live/quizzes/{id}` → `{id, pack_id, name, description, topic, owner_label, created_at, editable: true,
    questions: [{id, prompt, options, correct_option, time_limit_sec, points, sort_order, image_url, image_alt}]}`
    (active MC questions by sort_order, id). `PUT /{id}` `{name, description?, topic?, owner_label?}` (full replace).
  - `POST /{id}/questions` → 201 (appended: sort_order = max + 1); `PUT /{id}/questions/{qid}`. Body
    `{prompt 1–500, options 2–4 (trimmed, ≤200, no case-insensitive duplicates), correct_option,
    time_limit_sec 5–120 (default 20), points 100 | 200 ("double points", default 100), image_url?, image_alt?}` → 422
    otherwise. Questions are multiple_choice only. Another quiz's question id → 404.
  - `DELETE /{id}/questions/{qid}` → `{question_id, deleted, archived}`: hard delete by PK only if never used in
    live_question, class_turn, attempt, class_attempt or session_question; otherwise archive (`is_active = false`,
    hidden from the quiz). A game created at the same instant → FK → archive instead (game creation retries).
  - `PUT /{id}/order` `{question_ids}` = every active question exactly once → quiz (sort_order 1..n), else 422
    ("reload and retry"). Add/delete/reorder lock the pack row, so reorder vs delete serialise: either the reorder
    lands first (then the delete) or the stale reorder gets 422 — tested, never 500.
- `GET /api/live/packs` (header `X-Edit-Key`, comma-separated for several quizzes): seeded packs (`editable: false`)
  + the teacher's own quizzes (`editable: true`, listed first). **Teacher quizzes are unlisted without their key.**
  Items gain `editable`, `teacher_owned`, `owner_label`.
- **Private quizzes are never picked by "all packs" selection**: `POST /api/live/games` and
  `POST /api/class/sessions` with `pack_id` null, and individual `POST /api/sessions`, skip questions of packs with
  an edit key. A quiz is played only when its `pack_id` is chosen (no key needed to play).
- **Admin is DEPRECATED**: the `/admin` page route is removed (404; `static/admin.*` still on disk, to be deleted).
  `/api/admin/*` still work (tests use them) but no UI uses them — slated for removal.
  **→ REMOVED 2026-09-28:** `static/admin.*` and every `/api/admin/*` route are gone; tests seed packs/questions
  straight into the DB (`tests/_seed.py`).

## Classroom additions (app/classroom.py)
- multiple_choice attempt response: `feedback.correct_option` (0-based) and `feedback.correct_option_text` (safe: a
  quiz turn allows one attempt). Also stored in `class_attempt.feedback`.
- `PATCH /api/class/classrooms/{id}` `{name?, program?, is_archived?}` → classroom detail + `is_archived`
  (404 unknown; 422 blank/too-long name or non-bool). `GET /api/class/classrooms` hides archived classrooms unless
  `?include_archived=true`; list items gain `is_archived`. Archived classrooms stay reachable by id; data is kept.

## Test isolation on the shared dev DB
- Test suites put their questions in **private** packs (edit_key_hash set), so other users' "all packs" games can't
  pick them; teardowns delete by PK row by row and archive (never fail) a row someone else referenced meanwhile.

---
# SELF-PACED / HOMEWORK MODE (owner, 2026-09-28)
Owner: "student juga bisa ngerjain game session dibawa ke rumah, teacher ga harus selalu ngontrol terus, tapi bisa juga ngontrol".
Schema: `db/012_self_paced.sql` (locked; applied). Same tables as LIVE GAME; `live_game.mode = 'self_paced'`.

## Rules
- Create: `POST /api/live/games` gains `mode: 'live'|'self_paced'` (default live), `closes_at?` (ISO, must be future, ≤ 30 days),
  `speed_bonus?` (default **false** for self_paced, true for live), `shuffle_per_player?` (default false).
  Self-paced games start in status **`open`** immediately (no lobby/start); `instant_feedback` is always true.
- Player flow (per player, server-authoritative):
  - join (nickname) while `open` and not paused and not past `closes_at`.
  - `POST /games/{pin}/me/start` → sets `question_started_at = now()` for `current_idx` (idempotent: if already started, returns the
    same start; never resets the clock). Returns the question (public view, no answer).
  - `POST /games/{pin}/answer` must carry `idx == current_idx`; accepted until `question_started_at + time_limit + 3 s`;
    scored immediately (points use the speed factor only if `speed_bonus`), then `current_idx += 1`, `question_started_at = NULL`;
    after the last question `finished_at = now()`.
  - Timed out while away: on the next state read / start, a started-but-expired question is recorded as no answer (0 pts,
    streak unchanged) and the player advances. Unstarted questions never expire (a student can close the tab between questions).
  - One answer per player per idx (existing UNIQUE). All progress mutations lock the live_player row `FOR UPDATE`.
  - Refresh / come back later: player_token in localStorage resumes at `current_idx`.
- Teacher control (host token), all optional — nothing needs the teacher online:
  - `PATCH /games/{pin}/settings` gains `paused` (pause blocks join/start/answer; an in-flight question's clock is NOT
    extended — document; UI warns), `closes_at` (extend/shorten; past → effectively closed), plus existing `allow_rename`.
  - `POST /games/{pin}/end` closes (status ended). Kick / rename as in live.
  - Auto-close: a game past `closes_at` is treated as ended on read (lazy) — set status ended + ended_at on first read after the deadline.
- Host state for self_paced adds: `mode, closes_at, paused, progress: {joined, in_progress, finished},
  players: [{id, nickname, score, current_idx, total, finished_at, last_active_at}], per_question: [{idx, prompt, answered, correct_pct}]`,
  plus the leaderboard. Player state adds `mode, closes_at, paused, me.current_idx, me.total, me.finished_at, me.question_started_at, server_now`.
- SSE works as in live (host monitor updates live); the throttle applies.
- Reports / CSV: self-paced games are included; kind = `homework`; CSV adds `progress` and `finished_at`.

## Self-paced — implementation notes (as built, backend: `app/live_self_paced.py` + dispatch in `app/live.py`, tests `tests/test_self_paced.py`)
No new migration: `db/012_self_paced.sql` is enough (`last_active_at` is derived). Live-mode behaviour, shapes and
tests are unchanged (live states only gain `mode: "live"`).
- **Create** `POST /api/live/games` `{…, mode: "live"|"self_paced", closes_at?, speed_bonus?, shuffle_per_player?}`:
  `closes_at` ISO 8601 (naive = UTC), checked on the DB clock: must be in the future and ≤ 30 days from now (422);
  `null`/omitted = no deadline. `closes_at` or `shuffle_per_player: true` on a live game → 422. `speed_bonus` default
  false (self_paced) / true (live; `false` also works for live and drops the speed factor). `instant_feedback` is
  forced true for self_paced (a sent `false` is ignored at create). The game is created `status = 'open'`,
  `current_index = -1`, `phase_started_at = now`. Response (self_paced only) adds `mode`, `closes_at`.
  `/start` and `/next` on a self-paced game → 409.
- **Positions**: `me.current_idx` / the answer's `idx` / `question.idx` in the player state are the player's
  POSITION (0…total-1). With `shuffle_per_player` the position maps to `live_player.question_order[pos]` (a
  permutation of the live_question idx, drawn once at join, never changed); otherwise position = idx.
  `live_answer.idx` is always the REAL live_question idx.
- **`POST /games/{pin}/me/start`** (X-Player-Token) → player LiveState (with `question`). Error order 404 → 403
  (bad token / kicked) → 409 (not a self-paced game / ended / paused / finished). Idempotent: an already-running
  clock is returned unchanged. If the current question already expired it is recorded as no-answer first and
  the NEXT question is started.
- **Answer** (same endpoint as live): `idx` is REQUIRED (422 if missing; error order 404 → 403 → 422 missing idx →
  409 ended / paused / time up / finished / wrong idx / not started / already answered → 422 choice). Accepted
  while `clock_timestamp() - question_started_at ≤ time_limit_sec + 3 s`; `answer_ms` measured at receipt.
  Points = live formula; with `speed_bonus = false` the speed factor is 1.0 (`speed_factor: 1.0` stored). Stored
  with `applied = true` and added to score/streak in the SAME transaction that advances `current_idx` and clears
  `question_started_at` (`finished_at = now` after the last) — under FOR SHARE live_game + FOR UPDATE live_player,
  UNIQUE(game_id, idx, player_id) as the backstop. Response `{accepted, no_speech, result, current_idx, total,
  finished}` (`result` = own result incl. `correct`). Speaking questions work the same way (no-speech → nothing
  stored, retry until the deadline); an STT run that ends after a concurrent expiry → 409.
- **Timeouts (lazy)**: on the player's own `GET /state`, `/me/start` or `/answer`, a started question past
  `time_limit + 3 s` is recorded as **no answer**: NO live_answer row, 0 points, streak unchanged, `current_idx + 1`,
  `question_started_at = NULL`; on the last question `finished_at = question_started_at + limit + 3 s`. An
  `/answer` that triggers it gets 409 "Time is up" and the advance is still committed. Unstarted questions never
  expire. SSE streams only render (they don't expire): **clients call `GET /state` when `time_left_ms` hits 0.**
  Host monitor reads do not expire anybody (a student who walked away mid-question shows that question until
  they come back).
- **Pause** (`PATCH /settings {paused}`): join / start / answer → 409 "Game is paused by the teacher"; state reads,
  self-rename, kick/rename work. The running question's clock is NOT extended (it can expire during a pause).
  Public lookup: `joinable = false` while paused.
- **Deadline** (`PATCH /settings {closes_at}`): ≤ 30 days from now (422), `null` clears it, a past value closes the
  game at once (`status ended`, `ended_at = now`). **Lazy auto-close**: the first read / action after `closes_at`
  (any state read, SSE snapshot, join, start, answer, host action, public lookup) sets `status = 'ended'`,
  `ended_at = closes_at` (one conditional UPDATE, NOTIFY). An open SSE stream re-reads by itself when the deadline
  passes. `ended` is final: `paused` / `closes_at` changes → 409 (allow_rename still allowed). `instant_feedback:
  false` → 422; `paused` / `closes_at` on a live game → 422.
- `POST /end` → ended (idempotent). Kick / host rename / self-rename exactly as live.
- **Host LiveState (self_paced)**: `{game_id, pin, status ('open'|'ended'), title, mode: "self_paced", closes_at,
  paused, index: -1, total, phase_started_at: null, server_now, time_left_ms: null, settings: {allow_rename,
  instant_feedback: true, speed_bonus, shuffle_per_player}, question: null, players_count, answered_count (stored
  answers), reveal: null, progress: {joined, in_progress, finished}, players: [{id, nickname, score, current_idx,
  total, finished_at, last_active_at}] (join order), per_question: [{idx, prompt, answered, correct_pct}]
  (quiz order; correct_pct 0–100 1 decimal, null if nobody answered), leaderboard: {top ≤10 [{rank, player_id,
  nickname, score, delta_rank: 0}], rank_changes: []}, summary: {joined, answered_any}}`.
  `in_progress` = not finished and (current_idx > 0 or a question running); not-started = joined − in_progress −
  finished. `last_active_at` = latest of joined_at, running question start, last answer, finished_at. No correct
  answers anywhere in the host state.
- **Player LiveState (self_paced)**: same base keys; `index` = `me.current_idx`; `question` (public view, `idx` =
  position) + `time_left_ms` + `phase_started_at` only while the player's question is running (null before
  `/me/start`, so the prompt can't be read off the clock); `me: {id, nickname, score, rank, streak, current_idx,
  total, finished_at, question_started_at, answered_current: false, last_result}`; `last_result` = the player's own
  answer to the PREVIOUS position (with `correct`), null if none / timed out. `leaderboard: {top, me: {rank, score,
  above}}`. The only correct answer a player ever receives is for a question they have answered themselves.
- **CSV** (self_paced): live columns + `progress` (`"<current_idx>/<questions>"`) + `finished_at` (ISO, empty if
  not finished); filename `homework-<date>-<pin>.csv`.
- **Reports**: `live_game.mode = 'self_paced'`; a game with `status = 'open' AND closes_at <= now()` that nobody has
  read yet is effectively ended (lazy close) — treat it as ended. `current_index` is always -1; completion =
  `live_player.finished_at IS NOT NULL`; progress = `LEAST(current_idx, questions)`; timed-out questions have no
  live_answer row.

---
# TEACHER PRESENTS — INDIVIDUAL or GROUPS (owner, 2026-09-28)
Owner: "student ada case tidak punya device di sekolah… teachernya yang present, student2nya menjawab, teacher bisa input
nama individual dari student atau bisa menjadi kelompok belajar". Builds on CLASSROOM MODE (/api/class). Schema `db/013` (applied).

## Entry
`/host` create asks **"How will students play?"** → (1) *On their own devices* (PIN live) · (2) *Homework* (self-paced) ·
(3) *Teacher presents — no student devices* → **Individuals** | **Groups** → opens the presenter (`/classroom`) with the chosen
quiz + school pre-filled (query params `?pack=<id>&grouping=individual|teams`).

## grouping = 'teams' (existing behaviour)
Unchanged: 2–6 teams, captain per turn, team score.

## grouping = 'individual' (new)
- `POST /api/class/sessions` gains `grouping: 'teams'|'individual'` (default teams). For individual: `team_count`/`rounds`
  are ignored; `question_count` 1–50 (default 10) is required; `present_student_ids` ≥ 1 (max 60).
- Implementation reuses the existing tables: **one team row per present student** (team name = student name, position order =
  shuffled), `team_member` = that student. Colours/mascots cycle through the 5 brand colours.
- Queue: `question_count` turns. Each turn's *suggested* student = present student with the fewest turns (ties: stable random),
  same fairness rule as captains. The teacher may credit **any present student**: the attempt's `student_id` decides; the turn's
  `team_id` is re-pointed to that student's team in the same transaction (still FOR UPDATE on session + turn).
- Scoring: MCQ as in team mode (1 attempt, correct = passed); per-student streak = that student's consecutive correct turns.
- Late arrivals: `POST /api/class/sessions/{id}/students {names:[...]}` (both groupings) adds students to the classroom + attendance
  (present) and — individual: creates their team row; teams: puts each into the currently smallest team. Allowed while live.
- Host state (`SessionState`) gains `grouping`, and for individual a `leaderboard` (top 10 + total count) instead of a
  team scoreboard; finale ranking = per student; participation = present / answered at least once.
- Reports: kind stays `one-screen`; reports may show grouping.

## Presenter individual — implementation notes (as built, backend: `app/classroom.py`, tests `tests/test_presenter_individual.py`)
No new migration (`db/013` only). Team-mode behaviour, shapes and tests are unchanged; team SessionStates only gain
`grouping: "teams"` and `leaderboard: null`.
- **Create** `POST /api/class/sessions` `{classroom_id, pack_id?, game_modes?, grouping: "teams"|"individual"
  (default teams), …}`. individual: `question_count` **required** (1–50; omitted/null → 422 — the UI sends 10 by
  default), `present_student_ids` 1–60 after de-dupe (422), `team_count` / `rounds` ignored (not validated).
  teams: `team_count` required 2–6, `rounds` 1–10, ≥ team_count students; `question_count` ignored. Stored in
  `class_session.grouping` / `question_count` (null for teams). One team row per present student: `name` = the
  student's name, `position` 1..N = shuffled order, `emoji`/`color` cycle through the first 5 fixed entries
  (🐯 cyan, 🦅 pink, 🐬 lime, 🦊 amber, 🐘 violet); `team_member` = that student. Queue = `question_count` turns.
- **SessionState (individual)** = the team SessionState plus:
  `grouping: "individual"`,
  `teams: [{id, name, emoji, color, position, score, streak, members: [{student_id, name, turns_spoken}]}]` (one
  per student; `score`/`streak` are the student's),
  `turns[].team_id` = **null** while a turn is pending and unattempted (the stored team_id is only a placeholder),
  else the credited student's team,
  `next: {turn_no, team_id (suggested student's team), suggested_student_id} | null`,
  `leaderboard: {top: [≤10 {rank, student_id, team_id, name, emoji, color, score, streak, turns_spoken}],
  count: <present students>}` ordered score desc, name (case-insensitive), student_id; competition ranks
  (1, 1, 3). Teams states: `leaderboard: null`.
- **Suggestion**: the present student with the fewest `turns_spoken` (same definition as teams: attempted or
  charged with a skip), ties random but seeded by session + turn (stable across GETs); once the turn has an attempt
  it stays on that student. A late arrival (0 turns) can change the suggestion of a not-yet-attempted turn.
- **Attempt** `POST /sessions/{id}/turns/{n}/attempts`: any present student of the session may be credited. Error
  order: 404 → 409 finished / not current / attempts used ("one attempt for quiz") → **422 "Student is not present
  in this session"** → **409 "This turn was already answered by another student"** (speaking turn: the 2nd try
  must be the same student) → 422 choice/audio. Under the session + turn FOR UPDATE locks the turn's `team_id` is
  re-pointed to the student's team, `student_id` set, both the new and the old team recomputed (score =
  SUM(best_points), streak from history) — all in one transaction. Response unchanged (`team` = the student's
  team row).
- **Per-student streak** = the team streak of the student's own team = consecutive passed turns of that student
  (a wrong answer or a skip charged to them resets it). MCQ: 1 attempt, correct = passed, same compute_points.
- **next / skip (individual)**: `next` on an unattempted turn → `skipped` and **charged to the suggested
  student** (turn `student_id` + `team_id` set) so the rotation moves on; `skip {student_id?}` charges the named
  present student (422 "Student is not present in this session" otherwise) or, without one, the suggested
  student. Double "next" → one 200, one 409 (unchanged).
- `PUT /sessions/{id}/teams` on an individual session → **409** "Individual sessions have no teams to edit".
- **Late arrivals** `POST /api/class/sessions/{id}/students` `{names: string[1..100]}` (both groupings) → 200
  `{added: [{student_id, name, team_id, new_student}], skipped: [name], state: SessionState}`. 404 unknown session,
  **409 once finished**, 422 empty list. Locks the session row (serialises with attempt / next / skip) and then
  the classroom row. Names are trimmed + inner whitespace collapsed; blank ignored; in-paste duplicates dropped
  silently; matched **case-insensitively** against the classroom roster: unknown name → new student (added to the
  classroom, `new_student: true`); existing active student not yet present → marked present (attendance upsert,
  `new_student: false`); already present / inactive / > 100 chars → `skipped`. individual: a new team row at
  position max+1 (colour cycle continues); **422** if it would exceed 60 present students (nothing written).
  teams: joins the team with the fewest members (ties: lowest position), one name at a time.
- **Finish (individual)**: `ranking: [{student_id, team_id, name, emoji, color, score, rank}]` — every present
  student, leaderboard order, competition ranks; `mvp` as in teams (`team_id` = the student's team row);
  `participation: {present, spoke, rate, students: [...]}` with spoke = answered at least once; `students[].team`
  is **null** in individual mode (use `present`), ordered present first then by name.
- **CSV (individual)**: same columns; `team` empty; rows present first, then by name.
- **Reports**: unchanged queries work (per-student data comes from `class_turn.student_id`, `class_attempt`,
  `attendance`); kind stays `class` / type `one-screen`. `cs.grouping` is available for reports to show.

---
# REPORTS (program team) — `/reports`, `app/reports.py`, tests `tests/test_reports.py`
Read-only reporting across **all game kinds**, organised **School → game / class session → students**, plus a
name-matched progress view. Top-level KPIs are totals across all schools. Program is **no longer collected** (owner):
nothing is reported per program (see "Deprecated" below).

## Access
- Page `/reports` → `static/reports.html` (+ `reports.js`, `reports.css`; `theme-se.css` variables only). It asks for the
  reports access code and keeps it in `sessionStorage["reports.key"]` (this tab only; every access is in try/catch).
- Every `/api/reports/*` call needs header **`X-Reports-Key`**, compared in constant time: `hmac.compare_digest` of the
  sha256 digests of the given and expected key (the comparison also runs when the header is missing). Expected = env
  **`REPORTS_KEY`**, default **`reports123`** (dev prototype only; a WARNING is logged at startup while the default is used).
  **→ SUPERSEDED 2026-09-28:** no default any more; unset = 503 "reports not configured" (see FINAL CLEAN-UP).
  Missing / wrong key → **401**. **Failed** attempts are rate limited per IP: 10 failures / 300 s (env
  `REPORTS_FAIL_LIMIT`, `REPORTS_FAIL_WINDOW_SEC`) → **429** for every request from that IP (even with the right key) until
  the window passes. In-memory, per process, TCP peer IP (same caveats as the live join limiter → Redis when scaling out).
- **Monorepo:** this key becomes a **Better Auth session with a `program_manager` role** (no shared code).
- All queries run in a `READ ONLY` transaction, parameterised; SQL text is built only from constants in `app/reports.py`.

## Kinds
| kind (URL) | `type` label | source | school from |
|---|---|---|---|
| `live` | live | `live_game` with `mode = 'live'` + `live_player` / `live_answer` | `live_game.school` |
| `homework` | homework | `live_game` with `mode = 'self_paced'` (db/012) | `live_game.school` |
| `class` | one-screen | `class_session` + `attendance` / `class_attempt` / `class_turn` | `classroom.school` |

School is trimmed and grouped **case-insensitively**; the displayed spelling is the most common one. Blank → **`(not set)`**
(a real bucket in the schools list; `(not set)` also works as the `{school}` path value and as `school=` filter).

## Filters (all optional, all endpoints that list)
`school` (case-insensitive substring search; `%`/`_` are literal; `(not set)` = blank), `mode` = `all` | `live` |
`homework` | `one-screen` (alias `class`), `from` / `to` = inclusive dates `YYYY-MM-DD` on the session date
(`live_game.created_at` / `class_session.started_at`) in the DB timezone; `from > to` → 422.

## Metric definitions
- **Session** = one live game, homework game or class session matching the filters (any status, also unfinished).
- **Effective status** (shown in session lists / details): a homework game counts as `ended` when `status = 'ended'` OR
  (`mode = 'self_paced'` AND `closes_at IS NOT NULL` AND `closes_at <= now()`) — closing is lazy, so the stored status may
  still be `open`. Homework storage: a timed-out question has no `live_answer` row (answered = row count), progress =
  `LEAST(current_idx, questions)`, every player gets every question.
- **Participation row** = one person in one session: live/homework = a non-kicked `live_player`; one-screen = an
  `attendance` row with `present = true`. Kicked players are excluded everywhere.
- **participants** = unique people: live/homework players are anonymous per game, so each player row is one person;
  one-screen students are unique by `student.id`. **participated** = unique people with ≥ 1 stored answer (live/homework)
  or ≥ 1 `class_attempt` (one-screen). `participation_rate = participated / participants` (0–1, 4 decimals).
- **completed** (per participation row):
  - live: answered ≥ **80 %** of the questions the player was *present for*. present_for = questions played
    (`current_index + 1`, 0 in lobby) minus the questions that had already closed when the player joined (every question
    before the highest `idx` whose first answer is earlier than `joined_at`), and never less than what they answered.
    present_for 0 → not completed.
  - homework: `live_player.finished_at IS NOT NULL` (reached the end) — **completion % is the key homework metric**.
  - one-screen: took ≥ 1 turn AND the session was completed (`status = 'finished'` or no `pending` turn left).
- `joined` / `answered_any` / `completed` count participation rows (person × session); `completion_rate = completed /
  joined`. The **funnel** is joined → answered ≥ 1 → completed on that per-session basis (`pct` of joined).
- **avg_score_pct** = average accuracy (0–100, 2 decimals) over scored items: every stored live/homework answer, and for
  one-screen the best attempt of each turn a student took. Unanswered questions do not count as 0 (that is what completion
  measures). `null` when nothing was answered.
- **Session student table**: `answered` = stored answers (one-screen: turns attempted), `correct` = passed answers/turns,
  `accuracy_pct` = mean accuracy of those, `score` = `live_player.score` (one-screen: SUM `class_turn.best_points` credited
  to the student), `rank` = competition rank by score among present rows (1, 1, 3); absent students listed last with
  `rank: null`. Live rows add `present_for`; homework rows add `progress` (= `current_idx`, capped at total), `total`,
  `finished_at`.
- **Progress** (`/students`): people are matched **by name, approximate** — `lower()` of the trimmed, whitespace-collapsed
  nickname / student name within one school (players are anonymous nicknames, so two "Ben"s are one person and one child
  using two nicknames is two). Per person: every session attended in date order with its score % (null if nothing
  answered), `first_score_pct` / `last_score_pct` over scored sessions, `improvement_pct = last − first` (null with < 2
  scored sessions). The response and CSV say `matching: "name, approximate"`.

## API (prefix `/api/reports`, JSON unless `?format=csv`)
- `GET /summary` → `{filters, sessions, live_games, homework_games, class_sessions, schools (non-blank),
  sessions_school_not_set, participants, participated, participation_rate, joined, answered_any, completed,
  completion_rate, avg_score_pct, date_range:{from, to}, funnel:[{step: joined|answered|completed, count, pct}]}`.
- `GET /schools?sort=name|sessions|participants|participated|participation_rate|completion_rate|avg_score|last_session
  &dir=asc|desc&limit=1–200 (50)&offset=` → `{items:[{school, school_key, sessions, live_games, homework_games,
  class_sessions, participants, participated, participation_rate, joined, answered_any, completed, completion_rate,
  avg_score_pct, last_session_date}], total, limit, offset, sort, dir, filters}`; `(not set)` sorts last by name.
- `GET /schools/{school}/sessions?limit&offset` (exact case-insensitive school; newest first) → `{school, items:[{kind,
  type, id, title, date, started_at, teacher, school, status, grouping (one-screen: teams|individual, else null),
  questions, participants, participated, participation_rate, joined, answered_any, completed, completion_rate,
  avg_score_pct, csv_url, report_csv_url}], total, …}`. `csv_url` = the existing per-game CSV where one is reachable:
  one-screen → `/api/class/sessions/{id}/participation.csv`; live/homework → `null` (their `report.csv` needs the teacher's
  host token, which reports never hold) — `report_csv_url` (this API's session CSV) always works.
- `GET /sessions/{kind}/{id}?limit=1–500 (200)&offset` → `{session:{…as above}, students:[{id, name, present, answered,
  correct, accuracy_pct, score, rank, completed, …}], total, limit, offset}`. Unknown id or wrong kind → 404; bad kind /
  uuid → 422.
- `GET /students?school=` (required, exact) `&limit=1–200 (50)&offset` (pages are over people; one person's sessions are
  never split) → `{school, matching, note, items:[{name, match_key, sessions_attended, sessions_scored, first_score_pct,
  last_score_pct, improvement_pct, sessions:[{kind, type, session_id, date, title, name_as_entered, answered, score_pct,
  points}]}], total, …}`.
- **CSV** (`?format=csv` on each): UTF-8 with BOM, CRLF, whole filtered list up to 10 000 rows (limit/offset ignored).
  Filenames: `reports-summary-<school|all-schools>-<mode|all-modes>-<today>.csv` (one totals row),
  `reports-schools-<school search|all-schools>-<today>.csv`, `reports-sessions-<school>-<today>.csv`,
  `reports-students-<school>-<session date>-<kind>-<id8>.csv` (homework adds `progress`, `finished_at`),
  `reports-progress-<school>-<today>.csv` (column header says "matched by name, approximate"). No program columns.
- **Deprecated:** `program=` is still accepted (exact, case-insensitive, on the legacy `live_game.program` /
  `classroom.program` columns) so old links don't 422, but nothing depends on it, it is never reported, and there is no
  `(not set)` program bucket.

## Tests
Fixture rows use a per-run tag `[pytest-reports <run id>]` (schools, titles) and a random per-run year for all dates;
every assertion is scoped to that tag and/or year, so concurrent runs on the shared dev DB never double-count.
Rows are deleted by primary key.

## Indexes / performance
No new index (`db/011` was reserved but is **not needed**). EXPLAIN ANALYZE on a seeded volume inside a rolled-back
transaction (≈ 425 live games, 12 k players, 103 k answers, 183 class sessions): the first per-player (LATERAL) version
spent ~0.04 ms × 12 000 players walking `live_answer` backwards for "present for" (schools 706 ms); the set-based rewrite
(one GROUP BY per table, hash joins) runs schools in ≈ 300 ms, summary ≈ 100 ms, one school's sessions ≈ 12 ms, one
session ≈ 9 ms. Adding `live_answer (game_id, created_at) INCLUDE (idx)` and `live_answer (player_id)` changed nothing
measurable after the rewrite (300–390 ms vs 300–310 ms), so neither was added.
