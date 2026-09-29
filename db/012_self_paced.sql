-- Self-paced / homework games: students play at their own pace before a deadline; the teacher monitors and
-- can still control (pause, close, extend). Idempotent, non-destructive.

ALTER TABLE live_game ADD COLUMN IF NOT EXISTS mode         text        NOT NULL DEFAULT 'live';
ALTER TABLE live_game ADD COLUMN IF NOT EXISTS closes_at    timestamptz;          -- deadline (NULL = no deadline)
ALTER TABLE live_game ADD COLUMN IF NOT EXISTS paused       boolean     NOT NULL DEFAULT false;
ALTER TABLE live_game ADD COLUMN IF NOT EXISTS speed_bonus  boolean     NOT NULL DEFAULT true;  -- homework default false (set by API)
ALTER TABLE live_game ADD COLUMN IF NOT EXISTS shuffle_per_player boolean NOT NULL DEFAULT false;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'live_game_mode_check') THEN
    ALTER TABLE live_game ADD CONSTRAINT live_game_mode_check CHECK (mode IN ('live','self_paced'));
  END IF;
  -- self-paced games use status 'open' (accepting play) or 'ended'; widen the status check once.
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'live_game_status_check'
             AND pg_get_constraintdef(oid) NOT LIKE '%open%') THEN
    ALTER TABLE live_game DROP CONSTRAINT live_game_status_check;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'live_game_status_check') THEN
    ALTER TABLE live_game ADD CONSTRAINT live_game_status_check
      CHECK (status IN ('lobby','question','reveal','leaderboard','ended','open'));
  END IF;
END $$;

-- Per-player progress through the (shared or per-player shuffled) question list.
ALTER TABLE live_player ADD COLUMN IF NOT EXISTS current_idx          integer     NOT NULL DEFAULT 0;
ALTER TABLE live_player ADD COLUMN IF NOT EXISTS question_started_at  timestamptz;          -- server clock, set on /me/start
ALTER TABLE live_player ADD COLUMN IF NOT EXISTS finished_at          timestamptz;
ALTER TABLE live_player ADD COLUMN IF NOT EXISTS question_order       integer[];            -- only when shuffle_per_player

CREATE INDEX IF NOT EXISTS live_game_mode_status_idx ON live_game (mode, status, closes_at);
