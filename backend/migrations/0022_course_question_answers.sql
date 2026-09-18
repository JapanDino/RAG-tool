CREATE TABLE IF NOT EXISTS course_question_answers (
  id SERIAL PRIMARY KEY,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  citations JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  retrieval_method VARCHAR(255) NOT NULL,
  generation_provider VARCHAR(100) NOT NULL,
  generation_model VARCHAR(255),
  insufficient_context BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_course_question_answers_course_id ON course_question_answers(course_id);
CREATE INDEX IF NOT EXISTS ix_course_question_answers_insufficient_context ON course_question_answers(insufficient_context);
