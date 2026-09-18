CREATE TABLE IF NOT EXISTS course_copilot_suggestions (
  id SERIAL PRIMARY KEY,
  finding_id INT NOT NULL REFERENCES course_findings(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  audit_run_id INT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
  action_type VARCHAR(50) NOT NULL,
  title VARCHAR(500) NOT NULL,
  draft TEXT NOT NULL,
  target_bloom_level VARCHAR(50) NOT NULL,
  rationale TEXT NOT NULL,
  citations JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  retrieval_method VARCHAR(255) NOT NULL,
  generation_provider VARCHAR(100) NOT NULL,
  generation_model VARCHAR(255),
  insufficient_context BOOLEAN NOT NULL DEFAULT FALSE,
  status VARCHAR(50) NOT NULL DEFAULT 'draft',
  reviewed_by VARCHAR(255),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_course_copilot_suggestions_finding_id
  ON course_copilot_suggestions(finding_id);
CREATE INDEX IF NOT EXISTS ix_course_copilot_suggestions_course_id
  ON course_copilot_suggestions(course_id);
CREATE INDEX IF NOT EXISTS ix_course_copilot_suggestions_audit_run_id
  ON course_copilot_suggestions(audit_run_id);
CREATE INDEX IF NOT EXISTS ix_course_copilot_suggestions_status
  ON course_copilot_suggestions(status);
