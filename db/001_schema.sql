-- Speaking Game Prototype — schema (idempotent, non-destructive)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id          bigserial PRIMARY KEY,
  name        text        NOT NULL,
  email       text        NOT NULL UNIQUE,
  avatar      text        NOT NULL DEFAULT '🙂',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS question (
  id              bigserial PRIMARY KEY,
  game_mode       text        NOT NULL CHECK (game_mode IN ('read_aloud','repeat_after_me','picture_talk','quick_answer')),
  prompt          text        NOT NULL,
  target_text     text,
  keywords        text[]      NOT NULL DEFAULT '{}',
  image_url       text,
  difficulty      smallint    NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 3),
  base_points     integer     NOT NULL DEFAULT 100 CHECK (base_points BETWEEN 10 AND 1000),
  time_limit_sec  integer     NOT NULL DEFAULT 20 CHECK (time_limit_sec BETWEEN 5 AND 120),
  is_active       boolean     NOT NULL DEFAULT true,
  sort_order      integer     NOT NULL DEFAULT 0,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS question_mode_active_idx ON question (game_mode, is_active, sort_order);

CREATE TABLE IF NOT EXISTS game_session (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      bigint      NOT NULL REFERENCES users(id),
  game_mode    text        NOT NULL,
  started_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz,
  total_points integer     NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS game_session_user_idx ON game_session (user_id);

CREATE TABLE IF NOT EXISTS attempt (
  id                bigserial PRIMARY KEY,
  session_id        uuid        NOT NULL REFERENCES game_session(id),
  user_id           bigint      NOT NULL REFERENCES users(id),
  question_id       bigint      NOT NULL REFERENCES question(id),
  transcript        text        NOT NULL DEFAULT '',
  accuracy          numeric(5,2) NOT NULL,
  passed            boolean     NOT NULL,
  stars             smallint    NOT NULL,
  points            integer     NOT NULL,
  streak            integer     NOT NULL,
  duration_ms       integer     NOT NULL,
  feedback          jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS attempt_user_idx ON attempt (user_id);
CREATE INDEX IF NOT EXISTS attempt_session_idx ON attempt (session_id, id);
CREATE INDEX IF NOT EXISTS attempt_question_idx ON attempt (question_id);
