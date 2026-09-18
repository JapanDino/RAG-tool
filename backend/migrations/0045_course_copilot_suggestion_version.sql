ALTER TABLE course_copilot_suggestions
  ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE course_copilot_suggestions
  ADD CONSTRAINT ck_course_copilot_suggestions_version_positive
  CHECK (version >= 1);
