ALTER TABLE course_qa_feedback_events
  ADD COLUMN IF NOT EXISTS reviewed_by_user_id INT REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_course_qa_feedback_events_reviewed_by_user_id
  ON course_qa_feedback_events(reviewed_by_user_id);
