ALTER TABLE documents ADD COLUMN IF NOT EXISTS external_id VARCHAR(255);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS course_module_id INT REFERENCES course_modules(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_documents_external_id ON documents(external_id);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_course_module ON documents(course_module_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_dataset_content_hash
  ON documents(dataset_id, content_hash) WHERE content_hash IS NOT NULL;
