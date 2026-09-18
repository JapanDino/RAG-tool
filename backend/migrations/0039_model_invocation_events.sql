CREATE TABLE model_invocation_events (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  task VARCHAR(80) NOT NULL,
  workflow_version VARCHAR(100) NOT NULL,
  prompt_version VARCHAR(100) NOT NULL,
  model_alias VARCHAR(100) NOT NULL,
  status VARCHAR(20) NOT NULL,
  failure_class VARCHAR(40),
  latency_ms INT NOT NULL DEFAULT 0,
  input_tokens INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  validation_passed BOOLEAN NOT NULL DEFAULT FALSE,
  fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_model_invocation_events_status
    CHECK (status IN ('succeeded', 'fallback', 'failed')),
  CONSTRAINT ck_model_invocation_events_nonnegative
    CHECK (latency_ms >= 0 AND input_tokens >= 0 AND output_tokens >= 0)
);

CREATE INDEX ix_model_invocation_events_organization_id
  ON model_invocation_events(organization_id);
CREATE INDEX ix_model_invocation_events_task
  ON model_invocation_events(task);
CREATE INDEX ix_model_invocation_events_status
  ON model_invocation_events(status);
CREATE INDEX ix_model_invocation_events_failure_class
  ON model_invocation_events(failure_class);
CREATE INDEX ix_model_invocation_events_created_at
  ON model_invocation_events(created_at);
CREATE INDEX ix_model_invocation_events_org_created
  ON model_invocation_events(organization_id, created_at DESC);
