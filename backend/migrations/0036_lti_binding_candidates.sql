CREATE TABLE lti_binding_candidates (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  candidate_type VARCHAR(20) NOT NULL,
  identifier_digest VARCHAR(64) NOT NULL,
  platform_identifier VARCHAR(255),
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  seen_count INT NOT NULL DEFAULT 1,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  resolved_at TIMESTAMPTZ,
  resolved_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  target_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  target_course_id INT REFERENCES courses(id) ON DELETE SET NULL,
  CONSTRAINT ux_lti_binding_candidates_identifier
    UNIQUE (registration_id, candidate_type, identifier_digest),
  CONSTRAINT ck_lti_binding_candidates_type
    CHECK (candidate_type IN ('subject', 'context')),
  CONSTRAINT ck_lti_binding_candidates_status
    CHECK (status IN ('pending', 'bound', 'dismissed', 'expired'))
);
CREATE INDEX ix_lti_binding_candidates_registration_id ON lti_binding_candidates(registration_id);
CREATE INDEX ix_lti_binding_candidates_organization_id ON lti_binding_candidates(organization_id);
CREATE INDEX ix_lti_binding_candidates_candidate_type ON lti_binding_candidates(candidate_type);
CREATE INDEX ix_lti_binding_candidates_identifier_digest ON lti_binding_candidates(identifier_digest);
CREATE INDEX ix_lti_binding_candidates_status ON lti_binding_candidates(status);
CREATE INDEX ix_lti_binding_candidates_last_seen_at ON lti_binding_candidates(last_seen_at);
CREATE INDEX ix_lti_binding_candidates_expires_at ON lti_binding_candidates(expires_at);
CREATE INDEX ix_lti_binding_candidates_resolved_at ON lti_binding_candidates(resolved_at);
CREATE INDEX ix_lti_binding_candidates_resolved_by_user_id ON lti_binding_candidates(resolved_by_user_id);
CREATE INDEX ix_lti_binding_candidates_target_user_id ON lti_binding_candidates(target_user_id);
CREATE INDEX ix_lti_binding_candidates_target_course_id ON lti_binding_candidates(target_course_id);

CREATE TABLE lti_binding_events (
  id SERIAL PRIMARY KEY,
  organization_id INT REFERENCES organizations(id) ON DELETE SET NULL,
  registration_id INT REFERENCES lti_registrations(id) ON DELETE SET NULL,
  candidate_id INT REFERENCES lti_binding_candidates(id) ON DELETE SET NULL,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  event_type VARCHAR(20) NOT NULL,
  target_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  target_course_id INT REFERENCES courses(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_lti_binding_events_type CHECK (event_type IN ('bound', 'dismissed'))
);
CREATE INDEX ix_lti_binding_events_organization_id ON lti_binding_events(organization_id);
CREATE INDEX ix_lti_binding_events_registration_id ON lti_binding_events(registration_id);
CREATE INDEX ix_lti_binding_events_candidate_id ON lti_binding_events(candidate_id);
CREATE INDEX ix_lti_binding_events_actor_user_id ON lti_binding_events(actor_user_id);
CREATE INDEX ix_lti_binding_events_event_type ON lti_binding_events(event_type);
