CREATE TABLE lti_registration_events (
  id SERIAL PRIMARY KEY,
  organization_id INT REFERENCES organizations(id) ON DELETE SET NULL,
  registration_id INT REFERENCES lti_registrations(id) ON DELETE SET NULL,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  event_type VARCHAR(30) NOT NULL,
  changed_fields JSON NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_lti_registration_events_type
    CHECK (event_type IN ('created', 'updated', 'activated', 'deactivated'))
);
CREATE INDEX ix_lti_registration_events_organization_id
  ON lti_registration_events(organization_id);
CREATE INDEX ix_lti_registration_events_registration_id
  ON lti_registration_events(registration_id);
CREATE INDEX ix_lti_registration_events_actor_user_id
  ON lti_registration_events(actor_user_id);
CREATE INDEX ix_lti_registration_events_event_type
  ON lti_registration_events(event_type);
