ALTER TABLE canvas_oauth_attempts
  ADD COLUMN flow_kind VARCHAR(20) NOT NULL DEFAULT 'admin',
  ADD COLUMN product_session_id INT REFERENCES lti_product_sessions(id) ON DELETE CASCADE,
  ADD COLUMN course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  ADD COLUMN canvas_course_id VARCHAR(255),
  ADD CONSTRAINT ck_canvas_oauth_attempts_flow_context CHECK (
    (flow_kind = 'admin'
      AND product_session_id IS NULL
      AND course_id IS NULL
      AND canvas_course_id IS NULL)
    OR
    (flow_kind = 'instructor'
      AND product_session_id IS NOT NULL
      AND course_id IS NOT NULL
      AND canvas_course_id IS NOT NULL)
  );

CREATE INDEX ix_canvas_oauth_attempts_product_session_id
  ON canvas_oauth_attempts(product_session_id);
CREATE INDEX ix_canvas_oauth_attempts_course_id
  ON canvas_oauth_attempts(course_id);
CREATE INDEX ix_canvas_oauth_attempts_flow_kind
  ON canvas_oauth_attempts(flow_kind);
