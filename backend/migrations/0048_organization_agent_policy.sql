CREATE TABLE IF NOT EXISTS organization_agent_policies (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  learner_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  instructor_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  program_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  model_mode VARCHAR(50) NOT NULL DEFAULT 'approved_host_with_safe_fallback',
  version INT NOT NULL DEFAULT 1,
  updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_organization_agent_policies_org UNIQUE (organization_id),
  CONSTRAINT ck_organization_agent_policies_model_mode
    CHECK (model_mode IN ('approved_host_with_safe_fallback', 'deterministic_only'))
);

CREATE INDEX IF NOT EXISTS ix_organization_agent_policies_organization_id
  ON organization_agent_policies(organization_id);
CREATE INDEX IF NOT EXISTS ix_organization_agent_policies_updated_by_user_id
  ON organization_agent_policies(updated_by_user_id);

CREATE TABLE IF NOT EXISTS organization_agent_policy_events (
  id SERIAL PRIMARY KEY,
  policy_id INT NOT NULL REFERENCES organization_agent_policies(id) ON DELETE CASCADE,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  previous_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  new_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  version INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_organization_agent_policy_events_policy_id
  ON organization_agent_policy_events(policy_id);
CREATE INDEX IF NOT EXISTS ix_organization_agent_policy_events_organization_id
  ON organization_agent_policy_events(organization_id);
CREATE INDEX IF NOT EXISTS ix_organization_agent_policy_events_actor_user_id
  ON organization_agent_policy_events(actor_user_id);
