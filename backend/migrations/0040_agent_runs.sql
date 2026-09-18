CREATE TABLE agent_runs (
  id SERIAL PRIMARY KEY,
  public_id VARCHAR(64) NOT NULL UNIQUE,
  conversation_id VARCHAR(64) NOT NULL,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  course_id INT REFERENCES courses(id) ON DELETE SET NULL,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL,
  product_session_id INT REFERENCES lti_product_sessions(id) ON DELETE SET NULL,
  contract_version VARCHAR(20) NOT NULL,
  policy_version VARCHAR(40) NOT NULL,
  workflow VARCHAR(100),
  route_state VARCHAR(40) NOT NULL,
  status VARCHAR(20) NOT NULL,
  idempotency_digest VARCHAR(64) NOT NULL UNIQUE,
  label VARCHAR(200) NOT NULL,
  recovery_action VARCHAR(80),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ck_agent_runs_role CHECK (
    role IN ('student', 'instructor', 'methodologist', 'program_designer', 'administrator')
  ),
  CONSTRAINT ck_agent_runs_route_state CHECK (
    route_state IN ('routed', 'clarification_required', 'unsupported')
  ),
  CONSTRAINT ck_agent_runs_status CHECK (
    status IN (
      'queued', 'routing', 'tool_running', 'generating', 'awaiting_review',
      'completed', 'abstained', 'failed', 'cancelled'
    )
  ),
  CONSTRAINT ck_agent_runs_route_workflow CHECK (
    (route_state = 'routed' AND workflow IS NOT NULL)
    OR (route_state <> 'routed' AND workflow IS NULL)
  )
);

CREATE INDEX ix_agent_runs_conversation_id ON agent_runs(conversation_id);
CREATE INDEX ix_agent_runs_organization_id ON agent_runs(organization_id);
CREATE INDEX ix_agent_runs_course_id ON agent_runs(course_id);
CREATE INDEX ix_agent_runs_user_id ON agent_runs(user_id);
CREATE INDEX ix_agent_runs_role ON agent_runs(role);
CREATE INDEX ix_agent_runs_product_session_id ON agent_runs(product_session_id);
CREATE INDEX ix_agent_runs_route_state ON agent_runs(route_state);
CREATE INDEX ix_agent_runs_status ON agent_runs(status);
CREATE INDEX ix_agent_runs_created_at ON agent_runs(created_at);
CREATE INDEX ix_agent_runs_owner_conversation
  ON agent_runs(organization_id, user_id, role, conversation_id);

ALTER TABLE tutor_data_deletion_events
  ADD COLUMN agent_runs_deleted INT NOT NULL DEFAULT 0,
  ADD COLUMN agent_run_cutoff TIMESTAMPTZ;

ALTER TABLE tutor_data_deletion_events
  DROP CONSTRAINT ck_tutor_data_deletion_events_counts;
ALTER TABLE tutor_data_deletion_events
  ADD CONSTRAINT ck_tutor_data_deletion_events_counts
  CHECK (
    answers_deleted >= 0
    AND feedback_events_deleted >= 0
    AND agent_runs_deleted >= 0
  );
