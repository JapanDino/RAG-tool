CREATE TABLE IF NOT EXISTS datasets (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  dataset_id INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  title VARCHAR(300) NOT NULL,
  source VARCHAR(1000) NOT NULL,
  mime VARCHAR(100) DEFAULT 'text/plain',
  status VARCHAR(50) DEFAULT 'ready',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chunks (
  id SERIAL PRIMARY KEY,
  document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  idx INT NOT NULL DEFAULT 0,
  text TEXT NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS embeddings (
  id SERIAL PRIMARY KEY,
  chunk_id INT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  dim INT NOT NULL DEFAULT 1536,
  vec vector(1536),
  model VARCHAR(100) DEFAULT 'text-embedding-3-small',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_embeddings_vec ON embeddings USING ivfflat (vec) WITH (lists = 100);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='jobtype') THEN
    CREATE TYPE jobtype AS ENUM ('index','annotate','export');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='jobstatus') THEN
    CREATE TYPE jobstatus AS ENUM ('queued','running','done','failed');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='bloomlevel') THEN
    CREATE TYPE bloomlevel AS ENUM ('remember','understand','apply','analyze','evaluate','create');
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS bloom_annotations (
  id SERIAL PRIMARY KEY,
  chunk_id INT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  level bloomlevel NOT NULL,
  label VARCHAR(200) NOT NULL,
  rationale TEXT NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
  id SERIAL PRIMARY KEY,
  type jobtype NOT NULL,
  status jobstatus NOT NULL DEFAULT 'queued',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error TEXT
);
