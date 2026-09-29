-- Live game host settings + exactly-once score application. Idempotent, non-destructive.
-- See CONTRACT.md "Live — implementation notes".

-- Teacher settings (both default ON: "better than Kahoot").
ALTER TABLE live_game ADD COLUMN IF NOT EXISTS allow_rename     boolean NOT NULL DEFAULT true;
ALTER TABLE live_game ADD COLUMN IF NOT EXISTS instant_feedback boolean NOT NULL DEFAULT true;

-- live_answer.applied: its points/streak have been added to live_player (exactly once, in either mode).
-- Rows that existed before this migration belong to closed questions (already applied) -> added with DEFAULT true,
-- then the default for new rows becomes false (the app always sets it explicitly anyway).
ALTER TABLE live_answer ADD COLUMN IF NOT EXISTS applied boolean NOT NULL DEFAULT true;
ALTER TABLE live_answer ALTER COLUMN applied SET DEFAULT false;

-- Player self-rename cooldown (1 per 10 s), kept in the DB so it holds across workers/instances.
ALTER TABLE live_player ADD COLUMN IF NOT EXISTS renamed_at timestamptz;
