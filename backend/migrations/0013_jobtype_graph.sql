DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_type WHERE typname='jobtype') THEN
    BEGIN
      ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'graph';
    EXCEPTION
      WHEN duplicate_object THEN NULL;
    END;
  END IF;
END$$;

