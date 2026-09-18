ALTER TABLE agent_runs
  ADD COLUMN module_ref VARCHAR(160),
  ADD COLUMN selection_ref VARCHAR(160);
