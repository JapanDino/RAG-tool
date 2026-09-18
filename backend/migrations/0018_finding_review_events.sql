CREATE TABLE IF NOT EXISTS finding_review_events (
  id SERIAL PRIMARY KEY,
  finding_id INT NOT NULL REFERENCES course_findings(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  audit_run_id INT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
  from_status VARCHAR(50) NOT NULL,
  to_status VARCHAR(50) NOT NULL,
  reviewed_by VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_finding_review_events_finding ON finding_review_events(finding_id, created_at);
CREATE INDEX IF NOT EXISTS idx_finding_review_events_course ON finding_review_events(course_id, created_at);
