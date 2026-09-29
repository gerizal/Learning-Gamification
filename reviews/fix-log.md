# Fix log: a11y review + UX review (individual mode `/` → `/practice`, admin)

**Date:** 2026-09-28. **Engineer:** software-engineer agent.
**Inputs:** `reviews/a11y-review.md` (23 findings) and `reviews/ux-review.md` (24 findings).
**Contract:** see `CONTRACT.md` → "CHANGES AFTER REVIEW". **Migration:** `db/005_review_fixes.sql` (idempotent; applied twice to the dev DB).

**Verdict: verified with accepted limitations.** Every blocker is fixed and verified. Every major is fixed or partially fixed, except UX-06, which was descoped by the pivot, and UX-08, which is new features (proposed below). The limitations are listed under "Partially fixed / not fixed".

Scope changes during the work (coordinator messages):
1. **Kahoot pivot.** `/` becomes a landing page, and this game moves to `/practice` as a secondary experience. Findings that only concern its login, home dashboard or summary are marked **descoped (pivot)**. Where a fix was only a line or two, it was still done and the entry says so.
2. **Admin retired.** Teachers now edit questions in `/host`. All admin work was already finished and verified before this message arrived, so it stays in place, and those entries are marked **fixed, then descoped (admin retired)**. `admin.html`/`admin.js` were not touched after that message. The pack code from the classroom agent was merged, not overwritten.
3. Reusable pieces went into small modules for the live pages: `static/feedback.js`, `static/a11y-prefs.js`, and `recorder.js` (+ `peak`).

## Counts

| Review | Fixed | Partially fixed | Not fixed (descoped / new feature) |
|---|---|---|---|
| A11y (4 blocker · 7 major · 12 minor) | 20 | 2 (A11Y-09, A11Y-20) | 1 (A11Y-23, descoped: pivot) |
| UX (1 blocker · 10 major · 9 minor · 4 polish) | 15 | 5 (UX-05, UX-07, UX-09, UX-13, UX-19) | 4 (UX-06, UX-14, UX-22 descoped: pivot; UX-08 = new features, not built) |
| **Total (47)** | **35** | **7** | **5** |

All 4 a11y blockers and the UX blocker are **fixed and verified**.

## Evidence scripts (session scratchpad, reused from the reviewers' `a11y/lib.mjs` + `ux/*.wav`)
- `scratchpad/a11y/fix-verify.mjs`: learner game. Covers axe on every screen in both themes, 360 px, a keyboard-only round, timers, no-speech, quit and motion. Output: `fix-verify.log` / `fix-verify-out.json`. **133 PASS, 0 FAIL.**
- `scratchpad/a11y/fix-admin.mjs`: admin. Covers axe, aria-invalid, the CSV `;` separator, 360 px, order and toast position. Output: `fix-admin.log`. **22 PASS, 0 FAIL.**
- Screenshots: `reviews/shots/after-*.png` (login/home/play×4/result/summary × dark/light × 1280/360, plus timeup-choice, timer-off-recording, quick-auto-mic, no-speech, summary-stopped, keyboard-round-summary, quit-dialog, settings, result-retry, and admin-*).
- Test users `[fix] Tester 1–7` (ids 138–140, 200–203, 247, 249–251, 263, 264, 266 across the runs) were **deleted by primary key** after each run, together with their attempts, sessions and served rows. 0 `[fix]` users remain. No demo data was changed.

---

## A11y findings

| ID | Sev | Status | Where (file:line) | Evidence |
|---|---|---|---|---|
| A11Y-01 | blocker | **fixed** | `static/game.js:701` `setRecUi`: the mic is never `disabled`; it uses `aria-disabled` plus a click guard, and focus moves to the mic after start (`game.js` startRecording) | Keyboard-only round: "focus stayed on mic while recording in 5/5; Enter stopped 5/5". Space-start also moves focus to the mic. |
| A11Y-02 | blocker | **fixed** | `static/a11y-prefs.js` (`timer`: normal / long 2× / off, `timeLimitFor`); `game.js:782` `timeUp()` stops the mic and keeps the audio, then shows **Kirim rekaman / Rekam ulang** (`index.html:139`); settings dialog `index.html:193` | Time-up: "attempts sent=0, msg='Waktu habis. Rekamanmu belum dikirim…', focus=btn-send". Send gives exactly 1 attempt. 2×: "Waktu 40 detik". Off: still recording after 12.5 s on a 10 s question, 0 attempts. If the take was silent, only "Rekam ulang" is offered. Shots `after-timeup-choice.png`, `after-timer-off-recording.png`. |
| A11Y-03 | blocker | **fixed** | `game.js:637` "👁 Tampilkan teks" toggle (`aria-expanded`/`aria-controls`); pref "Tirukan Aku: tampilkan teks"; home card aria-label says "Butuh suara, atau pakai Tampilkan teks" | "text hidden→visible, aria-expanded=true" (4 runs) |
| A11Y-04 | blocker | **fixed** | `db/005` `question.image_alt`; `app/main.py` public/full view + PUT keeps it when omitted (`main.py:677`); `static/feedback.js` `describePicture()` (image_alt → Bahasa emoji names → prompt text, never "Gambar soal"); `game.js:649`; admin field `admin.html:343` | alt="Gambar: mobil, hujan", "Gambar: mi berkuah, sumpit". Test `test_admin_keyword_separators_and_image_alt`. Admin shows "image_alt field visible". |
| A11Y-05 | major | **fixed** | `game.js:1232` `spaceOwner`: Space is only taken when no control is focused. It can be turned off in settings (2.1.4). | "Space on Dengarkan: recording=false, tts calls=1". "Space on ✕: quit dialog=true, recording=false". Space on body still starts recording. |
| A11Y-06 | major | **fixed** | `game.js:690` idle status includes the limit ("Waktu 15 detik." / "Tanpa batas waktu."); a single polite "⏳ 5 detik lagi" in `#rec-status` | "'5 detik lagi' announced after 9.9s (limit 0:15)" |
| A11Y-07 | major | **fixed** | `static/feedback.js` `WORD_STATUS` glyphs ✓ ≈ ? ✗ + hidden label; legend swatches carry glyphs (`style.css:687`); missed = dotted underline, no strikethrough (`style.css:684`) | "glyphs ✓✓✓✓≈", "missed decoration none". Shot `after-result-dark-1280.png`. |
| A11Y-08 | major | **fixed** | Best attempt per question counts (`main.py:430` `_session_questions`, `main.py:578` finish); a retry shares the streak base (`scoring.py:175`); the summary shows "n dari m soal", not attempts (`game.js:1043`) | pytest `test_attempt_real_audio_best_attempt_counts`: avg = best accuracy, stars = best, a retry keeps streak 1 |
| A11Y-09 | major | **partially fixed** | Timer setting (A11Y-02). Speed bonus now needs ≥ 90 % (`scoring.py:229`), so short or cut-off takes aren't rewarded. No-speech carries no penalty. Retries are free (best counts). | **Not done:** "unclear counts as correct", a per-learner pass threshold, and a "Lewati soal" button. These are accommodation-profile features and are listed as a proposed feature. |
| A11Y-10 | major | **fixed** | `a11y-prefs.js` `reduceMotion()` = OS setting OR in-app "Kurangi animasi"; `html[data-motion="reduce"]` reuses the reduced-motion CSS (`style.css:743`); set before paint (`index.html` head) | default: loops `shine`,`wave` (juice kept); in-app: `[]`; OS: `[]`; toggling via the settings dialog with the keyboard sets `data-motion=reduce` |
| A11Y-11 | major | **fixed, then descoped (admin retired)** | `admin.html:95` badge colours #1d4ed8/#7e22ce/#0f766e/#c2410c; tab `.count` opacity removed; light ok/warn #166534/#92400e | axe admin list light + dark: **0 violations** (was 50 color-contrast nodes) |
| A11Y-12 | minor | **fixed** | `#result-title` is an `h1` (sr-only); `role=region` removed (`index.html:154`) | "h1=1 role=null"; axe result screens 0 |
| A11Y-13 | minor | **fixed** | `aria-live` removed from `#result-body`; one-sentence `#result-status` (role=status); count-up is outside any live region | result-status="Hasil: 3 bintang, akurasi 90%, +100 poin. Bonus cepat 10." |
| A11Y-14 | minor | **fixed** | judging branch sets `#rec-status` = "Menilai…" (`game.js:701`) | covered by live-region text in fix-verify |
| A11Y-15 | minor | **fixed** | "🔊 Dengarkan kalimat" has a stable name and no `aria-pressed`; "Memutar kalimat…" goes to `#rec-status` | "listen aria-pressed=null" |
| A11Y-16 | minor | **fixed** | `.theme-console .btn-sm` min 44×44 (`style.css:763`); toast close 44×44 (`style.css:306`); word/keyword buttons ≥ 44 px high | CSS |
| A11Y-17 | minor | **fixed** | "✕ Keluar" on the result screen; in-app `<dialog>` confirm with large buttons (`index.html:212`, `game.js:1097`); Esc returns focus | "quit visible on result"; "Esc on quit dialog returns focus to ✕"; axe quit dialog 0 |
| A11Y-18 | minor | **fixed** | light console `--warning:#92400e`, `--success:#166534` (`style.css:387`) | axe result-light 0 violations |
| A11Y-19 | minor | **fixed** | `feedback.js` `usefulExtraWords()` drops repeated target words and fillers; the rest is collapsed behind "Lihat detail" | shot `after-result-dark-1280.png` ("Lihat detail (4 kata lain terdengar)") |
| A11Y-20 | minor | **partially fixed** | Onboarding copy is neutral ("Butuh waktu lebih? Atur di ⚙️"); Bahasa headings "RONDE SELESAI!" / "RONDE DIHENTIKAN"; no "C" letter (💪 "Kamu makin lancar!"); "Sembunyikan papan juara" setting | S/A/B rank letters are kept (UX juice). The rest of the summary/home redesign is **descoped (pivot)**. |
| A11Y-21 | minor | **fixed, then descoped (admin retired)** | `admin.js:641` `linkError()`: `aria-invalid` + error id in `aria-describedby` | `[{"id":"f_prompt","d":"err_prompt promptHint","msg":"Prompt wajib diisi."}, …]`; axe editor 0 |
| A11Y-22 | minor | **fixed** | progress dots ✓/✗ glyph + shape (`game.js:558`, `style.css:567`); unearned stars have a visible outline (`style.css:646`) | shots `after-play-*`, `after-result-*` |
| A11Y-23 | minor | **not fixed: descoped (pivot)** | login "Pemain baru" inline errors | The login screen is secondary after the pivot |

## UX findings

| ID | Sev | Status | Where (file:line) | Evidence |
|---|---|---|---|---|
| UX-01 | blocker | **fixed** | `db/005` `session_question` + `attempt.awarded_points`; served check → 422 (`main.py:485`); best-per-question awarded points, streak over questions (`scoring.py:175`, `scoring.py:192`); retry label "poin terbaik yang dihitung"; result note "Poin terbaikmu … tetap N" / "🏅 Rekor baru" | pytest: retry `points_awarded==0`, streak stays 1, `session_total` = max; `test_attempt_on_question_not_served_is_422`; `test_streak_over_questions_and_complete_round`. UI: "Poin terbaikmu untuk soal ini tetap 21 — yang dihitung hanya percobaan terbaik". The reviewers' "inject a question" trick now gets 422. |
| UX-02 | major | **fixed** | finish returns `completed`, `rank` (null when incomplete), `questions_served/answered` (`main.py:578`); UI "RONDE DIHENTIKAN", no rank, no confetti, coin SFX only (`game.js:1043`) | "quit after 1: 'RONDE DIHENTIKAN', rank element=false, '1 dari 5 soal'"; pytest `completed False, rank None`; `test_completed_round_gets_rank` |
| UX-03 | major | **fixed** (a11y-safe) | `game.js:583` Jawab Cepat with timer "normal": a "SIAP? 3-2-1" countdown with the question veiled, then the mic opens automatically; `duration_ms` is measured from the reveal | "countdown visible=true, mic auto-opened". With timer 2× or off it stays tap-to-start (accessibility wins). |
| UX-04 | major | **fixed** | empty transcript → `status:"no_speech"`, nothing stored, streak and total unchanged (`main.py:505`); calm inline state on the play screen with no shake, sound or result (`game.js:848`); 0★ copy split (<30 % "Belum cocok…", 30–59 % "Hampir!") | "no-speech: stays on play screen=true, shake=false, combo x1.0"; pytest no-speech asserts; shot `after-no-speech.png` |
| UX-05 | major | **partially fixed** | tap any word or keyword to hear it at 0.7× (`feedback.js`); "🔊 Dengarkan contoh" in both alignment modes (`game.js:898`); no strikethrough | "tap word → speak('i')", "model sentence speak('I like to eat rice')". **Not done:** "kamu bilang *race*" under close words (needs the per-word spoken token from scoring) and "Latih 3 kata tersulit" (proposed feature). |
| UX-06 | major | **not fixed: descoped (pivot)** | home dashboard error handling | The home dashboard is secondary |
| UX-07 | major | **partially fixed** | leaderboard hides 0-point players (`main.py:629`); leaderboard sums best-per-question points, so it can't be farmed | Weekly board, "you ±2" and "Paling rajin" are **proposed features (not built)**; home is descoped (pivot) |
| UX-08 | major | **not fixed: new features** | n/a | See "Proposed features (not built)" |
| UX-09 | major | **partially fixed** | profile `recent` = best attempt per (session, question) with `target_text` and `attempts` (`main.py` `_profile`); UI shows the target sentence | One row per question per round, not per retry. Grouping by round with expand is **descoped (pivot)**. |
| UX-10 | major | **fixed** | backend `_clean_keywords` splits on `|` `;` `,` (`main.py:151`); admin `normKw` + CSV (`admin.js:65`, `:69`); importer help text | CSV preview "elephant;tree" → chips `elephant`, `tree`; `"four, 4"` → 2; pytest `["elephant;tree","big | grey","trunk, ears"]` → 6 keywords |
| UX-11 | major | **fixed** (privacy) | `GET /api/users`: no `email`, needs ≥ 2 characters, matches name or exact email, returns `email_masked` + `level` (`main.py:340`); profile `user` has no raw email; login shows "LV n · f***@example.test" | pytest `test_user_search_never_exposes_emails`; "login list: [fix] Tester 1 LV 1 · f***@example.test". "Recent players on this device" is descoped (pivot). |
| UX-12 | minor | **fixed** | `/api/games` has `min/max/avg_difficulty`, `difficulty` (`main.py:383`); cartridges show "Tingkat 1–2" (`game.js:402`) | pytest `test_games_list`; "Tingkat 1–2 \| … · 🔊" |
| UX-13 | minor | **partially fixed** | `#screen-play[data-mode]` drives the ring stroke, halo and recorder frame (`style.css:752`) | ring stroke `rgb(8,145,178)` for Baca Nyaring (light). The 400 ms "cartridge insert" transition was not built. |
| UX-14 | minor | **not fixed: descoped (pivot)** | rich summary | The API already returns `recap[]` (best per question) for a future recap UI |
| UX-15 | minor | **fixed** | speed bonus only at ≥ 90 % in individual mode (`scoring.py:229`, `SPEED_BONUS_MIN_ACCURACY`); classroom unchanged | `test_speed_bonus_needs_min_accuracy_when_asked` |
| UX-16 | minor | **fixed** | `game.js:196` maps status codes to Bahasa copy; raw `detail` goes to `console.warn` only | code; no English detail reaches toasts |
| UX-17 | minor | **fixed, then descoped (admin retired)** | `/api/admin/stats`: `plays`, `players`, avg and pass rate over the best attempt per play, `missed_words` (`main.py:714`); admin row shows "n pemain", "⚠ terlalu sulit", "Sering terlewat" (`admin.js:322`) | pytest: attempts=3, plays=1, players=1, pass_rate=100 |
| UX-18 | minor | **fixed, then descoped (admin retired)** | label "Urutan di daftar admin", hint "pemain mendapat soal acak" (`admin.html:372`) | fix-admin "Urutan di daftar admin" |
| UX-19 | minor | **partially fixed, then descoped (admin retired)** | ≤ 480 px 2-column compact rows (`admin.html:143`) | 490 → **264 px/question** at 360 px, no horizontal scroll; the ≤ 120 px "⋯ menu" target was not reached |
| UX-20 | minor | **fixed** | `game.js:695`: `pointer: coarse` → "Ketuk mikrofon, lalu bicara." (no Spasi) | "touch hint: 'Ketuk mikrofon, lalu bicara. Waktu 20 detik.'" |
| UX-21 | polish | **fixed** | `game.js:13` `GENERIC_PROMPT`: the generic English prompt is hidden, custom ones are kept | "Baca kalimat ini dengan suara jelas: On Sunday we…" (no "Read this sentence aloud") |
| UX-22 | polish | **not fixed: descoped (pivot)** | greeting toast on the login flow | n/a |
| UX-23 | polish | **fixed, then descoped (admin retired)** | admin toasts bottom-left (`admin.html:201`); API orders modes read_aloud → repeat → picture → quick (`main.py` `MODE_ORDER_SQL`) | "mode order read_aloud > repeat_after_me > picture_talk > quick_answer > multiple_choice"; "toast align flex-start" |
| UX-24 | polish | **fixed** | no `orb-breathe` loop while recording (`style.css:630`); the halo follows the voice level | the infinite-loop list on the play screen no longer has `orb-breathe` |

## Required backend changes (all in CONTRACT.md → "CHANGES AFTER REVIEW")
- The session score counts only the BEST attempt per question (`awarded_points`); streak is over questions; retries can't farm points or stars.
- `POST /api/attempts` → 422 for a question that wasn't served (`session_question`, db/005).
- Finish with unanswered questions → `completed:false`, `rank:null` (the UI shows "RONDE DIHENTIKAN").
- `recent` has `target_text`, one row per (session, question) = the best attempt.
- `image_alt` column + admin field; the picture alt uses it, else a Bahasa emoji description or the prompt, never "Gambar soal".
- `GET /api/users` never returns emails (masked only, ≥ 2 characters); profile `user` has no raw email either.
- `/api/games` returns a real difficulty per mode.
- No-speech → a distinct 200 `status:"no_speech"` with no penalty and nothing stored.
- CSV/API keywords: `|`, `;` and `,` are separators.
- Extra: leaderboard hides 0-point rows; speed bonus needs 3★ (individual only); admin stats use the best attempt per play and add `missed_words`; admin list follows learner mode order.

Shared helpers changed: `app/scoring.py` got new functions plus an optional `min_bonus_accuracy` (default 0), so **classroom scoring is unchanged**. `app/classroom.py` was not touched. `tests/test_classroom.py` is green, and so are the live agent's `test_live*.py`.

## Proposed features (not built)
- **Daily streak + daily goal:** store `last_played_date` per user and count consecutive days with ≥ 1 completed round; show "🔥 N hari" on home, with a daily goal of 1 round.
- **Daily challenge ("Tantangan hari ini"):** a date-seeded set of 5 mixed-mode questions, same for everyone that day, with 2× XP once per user per day (a `daily_challenge_claim(user_id, date)` row).
- **Level titles:** a static table (1 Pemula, 2 Pembicara, 3 Pencerita, 5 Bintang Panggung …) returned as `level_title` in the profile.
- **Unlockable avatars and cartridge skins:** a catalogue with `unlock_level` (LV 2/3/5), `PATCH /api/users/{id}` avatar validated against the unlocked set, and skins as CSS `--mode` palettes.
- **Weekly leaderboard:** `GET /api/leaderboard?period=week` (awarded points since Monday 00:00 local time), top 3 + "you ±2", a "Paling rajin" tab ranked by completed rounds this week, and a rank delta on the summary.
- **"Latih kata tersulit":** gather the non-correct words from the user's recent attempt feedback and build a 3-word drill round (TTS model + record each word, scored by alignment).
- **"Kamu bilang *race*":** return the spoken token paired with each `close` word from `score_alignment` and show it under the chip.
- **Comfortable-speaking profile ("Mode nyaman bicara", A11Y-09):** per-learner options for `unclear` = full credit, a lower pass threshold, and a no-penalty "Lewati soal" that doesn't break round completion.
- Built instead, because they're cheap and help learning: **tap-a-word-to-hear** and a **"Dengarkan contoh" model sentence** (speechSynthesis, offline).

## Commands run (final state)
- `for f in static/*.js; do node --check "$f"; done` → a11y-prefs.js, admin.js, classroom.js, feedback.js, game.js, recorder.js: all OK.
- `.venv/bin/python -m pytest -q` → **148 passed, 1 skipped** on the final run (includes test_api, test_scoring, test_classroom, test_live*; the skip is not in my tests).
- `psql … -f db/005_review_fixes.sql` twice → second run only "already exists, skipping" notices (idempotent).
- `GAME_PATH=/practice node scratchpad/a11y/fix-verify.mjs` (the game moved to `/practice` during the pivot, so the final run targets `/practice`) → **133 PASS / 0 FAIL, 0 console errors**. axe **0 violations** on login, home, play×4, result, summary, settings, quit dialog and time-up, in dark + light at 1280. No horizontal scroll at 360 on every screen. Keyboard-only full round done with the fake mic (`--use-file-for-fake-audio-capture` with the reviewers' `say` WAVs). An earlier run logged one `net::ERR_CONNECTION_CLOSED` while the shared `--reload` server restarted; the final run had none.
- `node scratchpad/a11y/fix-admin.mjs` → **22 PASS / 0 FAIL** (axe 0 on the admin gate, list, editor-with-errors and importer, in light + dark).
- The server on :8000 was never stopped. I didn't start any server.
