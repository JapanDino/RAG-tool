CREATE TABLE IF NOT EXISTS canvas_outcome_alignments (
  id SERIAL PRIMARY KEY,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  outcome_external_id VARCHAR(255) NOT NULL,
  assignment_external_id VARCHAR(255) NOT NULL,
  title VARCHAR(500),
  source_url VARCHAR(2000),
  submission_types JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_canvas_outcome_alignments_pair
    UNIQUE (course_id, outcome_external_id, assignment_external_id)
);

CREATE INDEX IF NOT EXISTS ix_canvas_outcome_alignments_course_id
  ON canvas_outcome_alignments(course_id);
CREATE INDEX IF NOT EXISTS ix_canvas_outcome_alignments_outcome_external_id
  ON canvas_outcome_alignments(outcome_external_id);
CREATE INDEX IF NOT EXISTS ix_canvas_outcome_alignments_assignment_external_id
  ON canvas_outcome_alignments(assignment_external_id);
