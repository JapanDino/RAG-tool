CREATE TABLE agent_tool_events (
  id SERIAL PRIMARY KEY,
  agent_run_id INT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  tool_name VARCHAR(100) NOT NULL,
  status VARCHAR(20) NOT NULL,
  latency_ms INT NOT NULL DEFAULT 0,
  failure_class VARCHAR(40),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ux_agent_tool_events_run_tool UNIQUE (agent_run_id, tool_name),
  CONSTRAINT ck_agent_tool_events_status CHECK (
    status IN ('succeeded', 'abstained', 'failed')
  ),
  CONSTRAINT ck_agent_tool_events_latency CHECK (latency_ms >= 0)
);

CREATE INDEX ix_agent_tool_events_agent_run_id
  ON agent_tool_events(agent_run_id);
CREATE INDEX ix_agent_tool_events_tool_name
  ON agent_tool_events(tool_name);
CREATE INDEX ix_agent_tool_events_status
  ON agent_tool_events(status);
CREATE INDEX ix_agent_tool_events_created_at
  ON agent_tool_events(created_at);
