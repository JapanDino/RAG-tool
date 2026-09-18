ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS feedback_status VARCHAR(50) NOT NULL DEFAULT 'unreviewed';
ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS feedback_comment TEXT;
ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(255);
ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_course_question_answers_feedback_status
  ON course_question_answers(feedback_status);

CREATE TABLE IF NOT EXISTS course_qa_feedback_events (
  id SERIAL PRIMARY KEY,
  answer_id INT NOT NULL REFERENCES course_question_answers(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  from_status VARCHAR(50) NOT NULL,
  to_status VARCHAR(50) NOT NULL,
  reviewed_by VARCHAR(255) NOT NULL,
  comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_course_qa_feedback_events_answer_id
  ON course_qa_feedback_events(answer_id);
CREATE INDEX IF NOT EXISTS ix_course_qa_feedback_events_course_id
  ON course_qa_feedback_events(course_id);
