-- Teacher-presents mode, individual variant: each student plays for themselves (no student devices). Idempotent.
ALTER TABLE class_session ADD COLUMN IF NOT EXISTS grouping       text    NOT NULL DEFAULT 'teams';
ALTER TABLE class_session ADD COLUMN IF NOT EXISTS question_count integer;             -- individual mode: fixed N questions
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'class_session_grouping_check') THEN
    ALTER TABLE class_session ADD CONSTRAINT class_session_grouping_check CHECK (grouping IN ('teams','individual'));
  END IF;
END $$;
