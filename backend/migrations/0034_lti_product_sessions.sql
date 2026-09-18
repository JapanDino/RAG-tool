CREATE TABLE lti_product_sessions (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL,
  token_digest VARCHAR(64) NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_lti_product_sessions_role CHECK (role IN ('student', 'instructor'))
);
CREATE INDEX ix_lti_product_sessions_registration_id ON lti_product_sessions(registration_id);
CREATE INDEX ix_lti_product_sessions_user_id ON lti_product_sessions(user_id);
CREATE INDEX ix_lti_product_sessions_course_id ON lti_product_sessions(course_id);
CREATE INDEX ix_lti_product_sessions_role ON lti_product_sessions(role);
CREATE INDEX ix_lti_product_sessions_token_digest ON lti_product_sessions(token_digest);
CREATE INDEX ix_lti_product_sessions_expires_at ON lti_product_sessions(expires_at);
CREATE INDEX ix_lti_product_sessions_revoked_at ON lti_product_sessions(revoked_at);
CREATE UNIQUE INDEX ux_lti_product_sessions_active_scope
  ON lti_product_sessions(registration_id, user_id, course_id)
  WHERE revoked_at IS NULL;
