# Content Guide: writing questions for the Classroom Quiz

This guide is for anyone who writes quiz questions: teachers in the quiz editor on `/host` (**Create a quiz**), or content
writers adding a ready-made pack as seed SQL (like `db/008_quiz_seed.sql`). It explains how answers are scored, so you
can write questions that are **fair to A1–A2 learners aged roughly 10–17**.

PlayClass is a Kahoot-style classroom quiz. **Every question is `multiple_choice`** (true/false is multiple choice with
two options). There are no speaking questions.

Scoring rules are defined in `CONTRACT.md` ("FINAL CLEAN-UP" and "LIVE GAME") and implemented in `app/scoring.py`.
This guide covers what those rules mean for content.

---

## 1. Multiple-choice quiz questions (`multiple_choice`)

### How it is scored
- The answer is correct (accuracy 100) or wrong (0). There is no partial credit.
- Points depend on speed: `base × (1 − 0.5 × answer_time ÷ time_limit)`. An instant correct answer earns about the full base; one right at the buzzer earns about half. A streak of correct answers adds up to +50%.
- Options appear as coloured tiles on the projector and on each student's device. The correct option is **never** sent to students before the reveal.

### Fields
| Field | Rule |
|---|---|
| `prompt` | The question, **≤ 100 characters** so it fits the projector at full size. |
| `options` | **2–4** answers, each **≤ 25 characters** (one tile). No duplicates, and no empty strings. |
| `correct_option` | **0-based** index into `options` (0 = first tile). |
| `difficulty` | 1–2 for the class packs. |
| `time_limit_sec` | **20** for a 4-option question, **15** for true/false. |
| `base_points` | **100**. |


### Writing good quiz questions
- **One clear idea per question.** Students read it on a projector from the back of the room. Use A2 words and short sentences, and avoid double negatives. If you use NOT, write it in capitals: "Which of these usually does NOT use AI?"
- **Exactly one answer is defensible.** If an expert could argue for two options, rewrite. Words like "usually", "probably" or "best first step" make judgement questions fair.
- **Plausible distractors.** Each wrong option should be something a learner might really think, for example a common grammar error ("She go to school."). Keep at most one light-hearted option per question ("It is magic"); younger students enjoy it, but it makes the question easier.
- **Similar length and form.** When the correct option is the only long one, students learn to pick the longest. Keep options grammatically parallel.
- **No "all of the above" / "none of the above".** They don't work well with shuffled tiles and they reward test tricks.
- **Mix the correct position.** Across a pack, each tile position (0–3) should be correct roughly equally often. In `008_quiz_seed.sql`, positions are spread with a seeded, balanced shuffle: 4/4/4/3 per 15 questions.
- **True/false:** `options` must be exactly `True|False` in that order, with `correct_option` 0 = True and 1 = False. Use about 5 per 20 questions, and balance True and False answers. Write statements that are clearly true or clearly false. Avoid "always" and "never" unless that is the point ("AI is always right." → False).
- **Teach something at the reveal.** The teacher explains the answer on the reveal screen, so choose facts worth one sentence of explanation ("Check it another way, because AI can make mistakes").
- **No invented facts.** No statistics, dates of product launches, or claims about specific policies. For AI packs, prefer habits and concepts (check facts, keep passwords private, a deepfake is a fake video made by AI) over trivia.
- **Brands and places:** allowed in the prompt only when they are part of daily life and neutral ("Google Maps" is fine in a teacher's script), but prefer generic wording in questions ("a map app").

### Coverage for AI packs (Apptitude: strictly AI topics)
Each AI pack should make the **practical relevance** visible: AI in maps, translation, recommendations, voice assistants and face unlock; AI at school and in jobs; scams, deepfakes and privacy; checking facts; and people making the final decision. The `ai-for-teachers` pack targets teachers themselves: lesson planning with AI, checking AI output (accuracy, level, bias, "hallucinations"), student data privacy, and classroom AI rules.

### Difficulty for quiz questions
| Difficulty | Question |
|---|---|
| **1** | A single everyday fact or habit; the distractors are clearly wrong for anyone who read the question. |
| **2** | Needs a little reasoning or vocabulary (*artificial*, *reliable*, *deepfake*), or grammar distractors that look similar. |

After a game, look at the reveal distribution on the projector or the per-session results in `/reports`. If fewer than about 30% of students answer a question correctly, it is probably badly worded; above about 95% it may be too easy for difficulty 2.

---

## 2. Where questions live

- **Teacher quizzes:** made and edited in `/host`. The editor enforces the rules above (2–4 options, no duplicates,
  one correct option, 5–120 s, 100 or 200 points). Each quiz belongs to the teacher who holds its edit key.
- **Ready-made packs:** seed SQL in `db/` (for example `db/008_quiz_seed.sql`). Every row needs `game_mode =
  'multiple_choice'`, `options` (2–4) and a 0-based `correct_option`. The seed files are idempotent, so they can be
  applied again. Never edit a migration that has already been applied: add a new numbered file instead.
- Older seed files (`002`, `004`) still contain speaking questions from before the quiz-only decision. They are never
  picked for a game and need no maintenance.

---

## 3. Topic rules

- **`ai` packs (Apptitude):** every question must be about AI: what it is, where we meet it, that it makes mistakes, that people decide, safe and smart use, and jobs. Everyday vocabulary is fine *inside* an AI context ("The phone can translate words for me").
- **`general` packs (Lenovo Malaysia):** any everyday topic.
- Keep claims simple and true. Don't state statistics, brand names or specific policies in questions.
- `why_it_matters` (pack level) is for **teachers**: 3–5 sentences in English, then `\n\n— BM —\n`, then the Bahasa Melayu version. Keep claims general and defensible.

---

## 4. Checklist before publishing a question

- [ ] Prompt ≤ 100 characters; 2–4 options, each ≤ 25 characters, no duplicates.
- [ ] Exactly one defensible answer; `correct_option` is 0-based and in range.
- [ ] No "all of the above" / "none of the above"; options have a similar length and form.
- [ ] True/false = `True|False` in that order, 15 s; 4 options = 20 s.
- [ ] Difficulty 1–2, time 15–25 s, base points 100.
- [ ] Across the pack, the correct position is spread over all tiles.
- [ ] The topic matches the pack (`ai` packs: strictly AI).
- [ ] Played once end to end in `/host` + `/play` before class.
