ALTER TABLE agent_runs
  ADD COLUMN input_digest VARCHAR(64);

UPDATE agent_runs
SET input_digest = idempotency_digest
WHERE input_digest IS NULL;

ALTER TABLE agent_runs
  ALTER COLUMN input_digest SET NOT NULL;
