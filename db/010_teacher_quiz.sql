-- Teacher-owned quizzes (no admin page): a question_pack with an edit key. Idempotent, non-destructive.
-- Only sha256(edit_key) is stored; seeded packs have edit_key_hash NULL (read-only; teachers duplicate them).
ALTER TABLE question_pack ADD COLUMN IF NOT EXISTS edit_key_hash text;
ALTER TABLE question_pack ADD COLUMN IF NOT EXISTS owner_label  text;
CREATE UNIQUE INDEX IF NOT EXISTS question_pack_edit_key_hash_uq ON question_pack (edit_key_hash)
  WHERE edit_key_hash IS NOT NULL;

-- Classroom cleanup: auto-created classes can be archived (hidden from "Use a saved class").
ALTER TABLE classroom ADD COLUMN IF NOT EXISTS is_archived boolean NOT NULL DEFAULT false;
