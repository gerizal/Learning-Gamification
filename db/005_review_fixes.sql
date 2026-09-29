-- Review fixes (reviews/a11y-review.md + reviews/ux-review.md) for INDIVIDUAL mode. Idempotent, non-destructive.
-- See CONTRACT.md "Changes after review".

-- A11Y-04: text alternative for the picture of picture_talk questions (admin-editable).
ALTER TABLE question ADD COLUMN IF NOT EXISTS image_alt text;

-- UX-01: the questions served by POST /api/sessions, in order. Attempts on other questions are rejected (422).
CREATE TABLE IF NOT EXISTS session_question (
  session_id   uuid     NOT NULL REFERENCES game_session(id),
  question_id  bigint   NOT NULL REFERENCES question(id),
  position     smallint NOT NULL,
  PRIMARY KEY (session_id, question_id)
);
CREATE INDEX IF NOT EXISTS session_question_pos_idx ON session_question (session_id, position);

-- UX-01: points this attempt actually ADDED to the session/profile total
-- (= max(0, attempt points - best points of earlier attempts on the same question in the session)).
-- NULL on attempts recorded before this migration; readers use COALESCE(awarded_points, points).
ALTER TABLE attempt ADD COLUMN IF NOT EXISTS awarded_points integer;
CREATE INDEX IF NOT EXISTS attempt_session_question_idx ON attempt (session_id, question_id);
