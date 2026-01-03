DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='jobs' AND column_name='task_id'
  ) THEN
    ALTER TABLE jobs ADD COLUMN task_id TEXT;
  END IF;
END$$;

CREATE INDEX IF NOT EXISTS ix_jobs_task_id ON jobs (task_id);
