ALTER TABLE course_copilot_suggestions
  ADD COLUMN IF NOT EXISTS review_reason VARCHAR(50);

CREATE INDEX IF NOT EXISTS ix_course_copilot_suggestions_review_reason
  ON course_copilot_suggestions(review_reason);
