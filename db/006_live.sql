-- Live game (Kahoot-style): teacher hosts, students join with a PIN on their own device. Idempotent.

-- New question type for quiz-style rounds (works in noisy rooms, fits AI-topic quizzes).
ALTER TABLE question ADD COLUMN IF NOT EXISTS options text[] NOT NULL DEFAULT '{}';
ALTER TABLE question ADD COLUMN IF NOT EXISTS correct_option smallint;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'question_game_mode_check'
             AND pg_get_constraintdef(oid) NOT LIKE '%multiple_choice%') THEN
    ALTER TABLE question DROP CONSTRAINT question_game_mode_check;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'question_game_mode_check') THEN
    ALTER TABLE question ADD CONSTRAINT question_game_mode_check
      CHECK (game_mode IN ('read_aloud','repeat_after_me','picture_talk','quick_answer','multiple_choice'));
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS live_game (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  pin              text        NOT NULL,                 -- 6 digits, unique among non-ended games
  host_token       text        NOT NULL,                 -- secret held by the teacher's browser
  title            text        NOT NULL DEFAULT '',
  teacher_name     text        NOT NULL DEFAULT '',
  school           text        NOT NULL DEFAULT '',
  program          text        NOT NULL DEFAULT '',
  pack_id          bigint      REFERENCES question_pack(id),
  status           text        NOT NULL DEFAULT 'lobby'
                   CHECK (status IN ('lobby','question','reveal','leaderboard','ended')),
  current_index    integer     NOT NULL DEFAULT -1,      -- index into live_question, -1 in lobby
  phase_started_at timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  ended_at         timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS live_game_active_pin_uq ON live_game (pin) WHERE status <> 'ended';

CREATE TABLE IF NOT EXISTS live_question (
  game_id      uuid     NOT NULL REFERENCES live_game(id),
  idx          integer  NOT NULL,
  question_id  bigint   NOT NULL REFERENCES question(id),
  PRIMARY KEY (game_id, idx)
);

CREATE TABLE IF NOT EXISTS live_player (
  id            bigserial   PRIMARY KEY,
  game_id       uuid        NOT NULL REFERENCES live_game(id),
  nickname      text        NOT NULL,
  player_token  text        NOT NULL,                  -- secret held by the student's browser
  score         integer     NOT NULL DEFAULT 0,
  streak        integer     NOT NULL DEFAULT 0,
  is_kicked     boolean     NOT NULL DEFAULT false,
  joined_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, nickname)
);

CREATE TABLE IF NOT EXISTS live_answer (
  id           bigserial    PRIMARY KEY,
  game_id      uuid         NOT NULL,
  idx          integer      NOT NULL,
  player_id    bigint       NOT NULL REFERENCES live_player(id),
  transcript   text         NOT NULL DEFAULT '',
  choice       smallint,                                -- multiple_choice only
  accuracy     numeric(5,2) NOT NULL,
  passed       boolean      NOT NULL,
  stars        smallint     NOT NULL,
  points       integer      NOT NULL,
  answer_ms    integer      NOT NULL,                   -- time from question start to submit (server clock)
  feedback     jsonb        NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz  NOT NULL DEFAULT now(),
  FOREIGN KEY (game_id, idx) REFERENCES live_question(game_id, idx),
  UNIQUE (game_id, idx, player_id)                      -- one answer per player per question
);
