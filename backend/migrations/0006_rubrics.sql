CREATE TABLE IF NOT EXISTS rubrics (
  id SERIAL PRIMARY KEY,
  level bloomlevel NOT NULL,
  name VARCHAR(200) NOT NULL,
  description TEXT NOT NULL,
  criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
  version INT NOT NULL DEFAULT 1,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rubrics_level ON rubrics (level);
CREATE INDEX IF NOT EXISTS idx_rubrics_is_active ON rubrics (is_active);
CREATE INDEX IF NOT EXISTS idx_rubrics_level_active ON rubrics (level, is_active);

