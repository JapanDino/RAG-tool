ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS asked_by_user_id INT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS response_mode VARCHAR(50) NOT NULL DEFAULT 'answer';
ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS policy_reason VARCHAR(100);

CREATE INDEX IF NOT EXISTS ix_course_question_answers_asked_by_user_id
  ON course_question_answers(asked_by_user_id);
CREATE INDEX IF NOT EXISTS ix_course_question_answers_response_mode
  ON course_question_answers(response_mode);
CREATE INDEX IF NOT EXISTS ix_course_question_answers_policy_reason
  ON course_question_answers(policy_reason);

ALTER TABLE course_question_answers
  DROP CONSTRAINT IF EXISTS ck_course_question_answers_response_mode;
ALTER TABLE course_question_answers
  ADD CONSTRAINT ck_course_question_answers_response_mode
  CHECK (response_mode IN ('answer', 'guidance', 'abstained'));
