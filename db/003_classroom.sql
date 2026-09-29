-- Classroom mode (game master + teams, 1 device + 1 mic in class). Idempotent, non-destructive.

CREATE TABLE IF NOT EXISTS question_pack (
  id              bigserial PRIMARY KEY,
  slug            text        NOT NULL UNIQUE,
  name            text        NOT NULL,
  topic           text        NOT NULL CHECK (topic IN ('ai','general')),
  description     text        NOT NULL DEFAULT '',
  why_it_matters  text        NOT NULL DEFAULT '',   -- teacher-facing: why teach this (esp. AI topic)
  is_active       boolean     NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE question ADD COLUMN IF NOT EXISTS pack_id bigint REFERENCES question_pack(id);
CREATE INDEX IF NOT EXISTS question_pack_idx ON question (pack_id, game_mode, is_active);

CREATE TABLE IF NOT EXISTS classroom (
  id            bigserial PRIMARY KEY,
  name          text        NOT NULL,
  school        text        NOT NULL DEFAULT '',
  teacher_name  text        NOT NULL DEFAULT '',
  program       text        NOT NULL DEFAULT '',     -- e.g. 'Lenovo Malaysia', 'Apptitude'
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS student (
  id            bigserial PRIMARY KEY,
  classroom_id  bigint      NOT NULL REFERENCES classroom(id),
  name          text        NOT NULL,
  is_active     boolean     NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (classroom_id, name)
);

CREATE TABLE IF NOT EXISTS class_session (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  classroom_id        bigint      NOT NULL REFERENCES classroom(id),
  pack_id             bigint      REFERENCES question_pack(id),
  game_modes          text[]      NOT NULL,
  status              text        NOT NULL DEFAULT 'live' CHECK (status IN ('live','finished')),
  current_turn        integer     NOT NULL DEFAULT 1,
  started_at          timestamptz NOT NULL DEFAULT now(),
  finished_at         timestamptz
);
CREATE INDEX IF NOT EXISTS class_session_classroom_idx ON class_session (classroom_id, started_at);

CREATE TABLE IF NOT EXISTS team (
  id                bigserial PRIMARY KEY,
  class_session_id  uuid        NOT NULL REFERENCES class_session(id),
  name              text        NOT NULL,
  emoji             text        NOT NULL,
  color             text        NOT NULL,          -- token name e.g. 'cyan','pink','lime','amber','violet','orange'
  position          smallint    NOT NULL,
  score             integer     NOT NULL DEFAULT 0,
  streak            integer     NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS team_session_idx ON team (class_session_id, position);

CREATE TABLE IF NOT EXISTS team_member (
  team_id     bigint NOT NULL REFERENCES team(id),
  student_id  bigint NOT NULL REFERENCES student(id),
  PRIMARY KEY (team_id, student_id)
);

CREATE TABLE IF NOT EXISTS attendance (
  class_session_id  uuid    NOT NULL REFERENCES class_session(id),
  student_id        bigint  NOT NULL REFERENCES student(id),
  present           boolean NOT NULL DEFAULT true,
  PRIMARY KEY (class_session_id, student_id)
);

-- The planned queue: one row per turn (team + question), created at session start.
CREATE TABLE IF NOT EXISTS class_turn (
  class_session_id  uuid        NOT NULL REFERENCES class_session(id),
  turn_no           integer     NOT NULL,
  team_id           bigint      NOT NULL REFERENCES team(id),
  question_id       bigint      NOT NULL REFERENCES question(id),
  status            text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','skipped')),
  student_id        bigint      REFERENCES student(id),   -- who actually spoke (set on attempt/skip)
  best_points       integer     NOT NULL DEFAULT 0,
  PRIMARY KEY (class_session_id, turn_no)
);

CREATE TABLE IF NOT EXISTS class_attempt (
  id                bigserial PRIMARY KEY,
  class_session_id  uuid        NOT NULL,
  turn_no           integer     NOT NULL,
  attempt_no        smallint    NOT NULL CHECK (attempt_no BETWEEN 1 AND 2),
  student_id        bigint      NOT NULL REFERENCES student(id),
  transcript        text        NOT NULL DEFAULT '',
  accuracy          numeric(5,2) NOT NULL,
  passed            boolean     NOT NULL,
  stars             smallint    NOT NULL,
  points            integer     NOT NULL,
  duration_ms       integer     NOT NULL,
  feedback          jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (class_session_id, turn_no) REFERENCES class_turn(class_session_id, turn_no),
  UNIQUE (class_session_id, turn_no, attempt_no)
);
CREATE INDEX IF NOT EXISTS class_attempt_student_idx ON class_attempt (student_id);
