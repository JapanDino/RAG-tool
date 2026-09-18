CREATE TABLE canvas_oauth_configurations (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  canvas_api_origin VARCHAR(1000) NOT NULL,
  oauth_client_id VARCHAR(255) NOT NULL,
  version INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_canvas_oauth_configurations_registration UNIQUE (registration_id),
  CONSTRAINT ck_canvas_oauth_configurations_version CHECK (version > 0)
);
CREATE INDEX ix_canvas_oauth_configurations_registration_id
  ON canvas_oauth_configurations(registration_id);
CREATE INDEX ix_canvas_oauth_configurations_organization_id
  ON canvas_oauth_configurations(organization_id);

CREATE TABLE canvas_oauth_attempts (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  state_digest VARCHAR(64) NOT NULL UNIQUE,
  redirect_uri VARCHAR(2000) NOT NULL,
  canvas_api_origin VARCHAR(1000) NOT NULL,
  oauth_client_id VARCHAR(255) NOT NULL,
  requested_scopes JSON NOT NULL DEFAULT '[]',
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_canvas_oauth_attempts_registration_id
  ON canvas_oauth_attempts(registration_id);
CREATE INDEX ix_canvas_oauth_attempts_organization_id
  ON canvas_oauth_attempts(organization_id);
CREATE INDEX ix_canvas_oauth_attempts_user_id ON canvas_oauth_attempts(user_id);
CREATE INDEX ix_canvas_oauth_attempts_state_digest ON canvas_oauth_attempts(state_digest);
CREATE INDEX ix_canvas_oauth_attempts_expires_at ON canvas_oauth_attempts(expires_at);
CREATE INDEX ix_canvas_oauth_attempts_consumed_at ON canvas_oauth_attempts(consumed_at);

CREATE TABLE canvas_oauth_connections (
  id SERIAL PRIMARY KEY,
  registration_id INT NOT NULL REFERENCES lti_registrations(id) ON DELETE CASCADE,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  canvas_api_origin VARCHAR(1000) NOT NULL,
  granted_scopes JSON NOT NULL DEFAULT '[]',
  vault_reference VARCHAR(255) NOT NULL UNIQUE,
  connection_mode VARCHAR(30) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  connected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_canvas_oauth_connections_user UNIQUE (registration_id, user_id),
  CONSTRAINT ck_canvas_oauth_connections_mode
    CHECK (connection_mode IN ('fake_development'))
);
CREATE INDEX ix_canvas_oauth_connections_registration_id
  ON canvas_oauth_connections(registration_id);
CREATE INDEX ix_canvas_oauth_connections_organization_id
  ON canvas_oauth_connections(organization_id);
CREATE INDEX ix_canvas_oauth_connections_user_id ON canvas_oauth_connections(user_id);
CREATE INDEX ix_canvas_oauth_connections_expires_at ON canvas_oauth_connections(expires_at);
CREATE INDEX ix_canvas_oauth_connections_revoked_at ON canvas_oauth_connections(revoked_at);

CREATE TABLE canvas_oauth_events (
  id SERIAL PRIMARY KEY,
  organization_id INT REFERENCES organizations(id) ON DELETE SET NULL,
  registration_id INT REFERENCES lti_registrations(id) ON DELETE SET NULL,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  event_type VARCHAR(30) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_canvas_oauth_events_type
    CHECK (event_type IN ('configured', 'connected', 'disconnected'))
);
CREATE INDEX ix_canvas_oauth_events_organization_id ON canvas_oauth_events(organization_id);
CREATE INDEX ix_canvas_oauth_events_registration_id ON canvas_oauth_events(registration_id);
CREATE INDEX ix_canvas_oauth_events_actor_user_id ON canvas_oauth_events(actor_user_id);
CREATE INDEX ix_canvas_oauth_events_event_type ON canvas_oauth_events(event_type);
