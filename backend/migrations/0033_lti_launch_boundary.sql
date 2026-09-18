CREATE TABLE lti_registrations (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  issuer VARCHAR(1000) NOT NULL,
  client_id VARCHAR(255) NOT NULL,
  deployment_id VARCHAR(255) NOT NULL,
  authorization_endpoint VARCHAR(2000) NOT NULL,
  jwks_url VARCHAR(2000) NOT NULL,
  tool_launch_url VARCHAR(2000) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_development BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_lti_registrations_platform_deployment
    UNIQUE (issuer, client_id, deployment_id)
);
CREATE INDEX ix_lti_registrations_organization_id ON lti_registrations(organization_id);
CREATE INDEX ix_lti_registrations_issuer ON lti_registrations(issuer);
CREATE INDEX ix_lti_registrations_client_id ON lti_registrations(client_id);
CREATE INDEX ix_lti_registrations_deployment_id ON lti_registrations(deployment_id);
CREATE INDEX ix_lti_registrations_is_active ON lti_registrations(is_active);
CREATE INDEX ix_lti_registrations_is_development ON lti_registrations(is_development);

CREATE TABLE lti_subject_bindings (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  platform_subject VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_lti_subject_bindings_sub UNIQUE (registration_id, platform_subject),
  CONSTRAINT ux_lti_subject_bindings_user UNIQUE (registration_id, user_id)
);
CREATE INDEX ix_lti_subject_bindings_registration_id ON lti_subject_bindings(registration_id);
CREATE INDEX ix_lti_subject_bindings_user_id ON lti_subject_bindings(user_id);
CREATE INDEX ix_lti_subject_bindings_platform_subject ON lti_subject_bindings(platform_subject);

CREATE TABLE lti_context_bindings (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  platform_context_id VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_lti_context_bindings_context
    UNIQUE (registration_id, platform_context_id),
  CONSTRAINT ux_lti_context_bindings_course UNIQUE (registration_id, course_id)
);
CREATE INDEX ix_lti_context_bindings_registration_id ON lti_context_bindings(registration_id);
CREATE INDEX ix_lti_context_bindings_course_id ON lti_context_bindings(course_id);
CREATE INDEX ix_lti_context_bindings_platform_context_id ON lti_context_bindings(platform_context_id);

CREATE TABLE lti_launch_attempts (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  state_digest VARCHAR(64) NOT NULL UNIQUE,
  nonce_digest VARCHAR(64) NOT NULL,
  target_link_uri VARCHAR(2000) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_lti_launch_attempts_registration_id ON lti_launch_attempts(registration_id);
CREATE INDEX ix_lti_launch_attempts_state_digest ON lti_launch_attempts(state_digest);
CREATE INDEX ix_lti_launch_attempts_expires_at ON lti_launch_attempts(expires_at);
CREATE INDEX ix_lti_launch_attempts_consumed_at ON lti_launch_attempts(consumed_at);

CREATE TABLE lti_launch_audit_events (
  id SERIAL PRIMARY KEY,
  registration_id INT REFERENCES lti_registrations(id) ON DELETE SET NULL,
  organization_id INT REFERENCES organizations(id) ON DELETE SET NULL,
  course_id INT REFERENCES courses(id) ON DELETE SET NULL,
  user_id INT REFERENCES users(id) ON DELETE SET NULL,
  outcome VARCHAR(20) NOT NULL,
  reason_code VARCHAR(50) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_lti_launch_audit_events_registration_id ON lti_launch_audit_events(registration_id);
CREATE INDEX ix_lti_launch_audit_events_organization_id ON lti_launch_audit_events(organization_id);
CREATE INDEX ix_lti_launch_audit_events_course_id ON lti_launch_audit_events(course_id);
CREATE INDEX ix_lti_launch_audit_events_user_id ON lti_launch_audit_events(user_id);
CREATE INDEX ix_lti_launch_audit_events_outcome ON lti_launch_audit_events(outcome);
CREATE INDEX ix_lti_launch_audit_events_reason_code ON lti_launch_audit_events(reason_code);
