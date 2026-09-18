CREATE TABLE IF NOT EXISTS course_tutor_policies (
  id SERIAL PRIMARY KEY,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  answer_style VARCHAR(50) NOT NULL DEFAULT 'balanced',
  version INT NOT NULL DEFAULT 1,
  updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_course_tutor_policies_course UNIQUE (course_id),
  CONSTRAINT ck_course_tutor_policies_style
    CHECK (answer_style IN ('balanced', 'guided', 'concise'))
);

CREATE INDEX IF NOT EXISTS ix_course_tutor_policies_course_id
  ON course_tutor_policies(course_id);
CREATE INDEX IF NOT EXISTS ix_course_tutor_policies_answer_style
  ON course_tutor_policies(answer_style);
CREATE INDEX IF NOT EXISTS ix_course_tutor_policies_updated_by_user_id
  ON course_tutor_policies(updated_by_user_id);

CREATE TABLE IF NOT EXISTS course_tutor_policy_events (
  id SERIAL PRIMARY KEY,
  policy_id INT NOT NULL REFERENCES course_tutor_policies(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  previous_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  new_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  version INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_course_tutor_policy_events_policy_id
  ON course_tutor_policy_events(policy_id);
CREATE INDEX IF NOT EXISTS ix_course_tutor_policy_events_course_id
  ON course_tutor_policy_events(course_id);
CREATE INDEX IF NOT EXISTS ix_course_tutor_policy_events_actor_user_id
  ON course_tutor_policy_events(actor_user_id);

ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS tutor_policy_version INT NOT NULL DEFAULT 0;
ALTER TABLE course_question_answers
  ADD COLUMN IF NOT EXISTS tutor_answer_style VARCHAR(50) NOT NULL DEFAULT 'balanced';

CREATE INDEX IF NOT EXISTS ix_course_question_answers_tutor_answer_style
  ON course_question_answers(tutor_answer_style);
