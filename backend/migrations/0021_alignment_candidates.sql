CREATE TABLE IF NOT EXISTS alignment_candidates (
  id SERIAL PRIMARY KEY,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  audit_run_id INT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
  source_type VARCHAR(50) NOT NULL,
  source_id INT NOT NULL,
  target_type VARCHAR(50) NOT NULL,
  target_id INT NOT NULL,
  relation_type VARCHAR(50) NOT NULL,
  score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  selected BOOLEAN NOT NULL DEFAULT FALSE,
  method VARCHAR(100) NOT NULL,
  model_info JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_alignment_candidates_pair
    UNIQUE (audit_run_id, source_id, target_id, relation_type)
);

CREATE INDEX IF NOT EXISTS ix_alignment_candidates_course_id ON alignment_candidates(course_id);
CREATE INDEX IF NOT EXISTS ix_alignment_candidates_audit_run_id ON alignment_candidates(audit_run_id);
CREATE INDEX IF NOT EXISTS ix_alignment_candidates_relation_type ON alignment_candidates(relation_type);
CREATE INDEX IF NOT EXISTS ix_alignment_candidates_score ON alignment_candidates(score);
CREATE INDEX IF NOT EXISTS ix_alignment_candidates_selected ON alignment_candidates(selected);
