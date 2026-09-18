CREATE TABLE IF NOT EXISTS course_evaluation_protocols (
  id SERIAL PRIMARY KEY,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  status VARCHAR(50) NOT NULL,
  protocol_version VARCHAR(100) NOT NULL,
  dataset_name VARCHAR(255) NOT NULL,
  dataset_hash VARCHAR(64) NOT NULL,
  thresholds JSONB NOT NULL DEFAULT '{}'::jsonb,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  checks JSONB NOT NULL DEFAULT '[]'::jsonb,
  methodology JSONB NOT NULL DEFAULT '[]'::jsonb,
  duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_course_evaluation_protocols_course_id
  ON course_evaluation_protocols(course_id);
CREATE INDEX IF NOT EXISTS ix_course_evaluation_protocols_status
  ON course_evaluation_protocols(status);
CREATE INDEX IF NOT EXISTS ix_course_evaluation_protocols_dataset_hash
  ON course_evaluation_protocols(dataset_hash);
