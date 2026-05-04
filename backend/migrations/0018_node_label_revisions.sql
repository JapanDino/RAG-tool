ALTER TABLE node_labels
  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;

-- Add updated_at WITHOUT a DEFAULT so pre-existing rows receive NULL rather
-- than the migration execution timestamp.  Back-fill from created_at first,
-- then attach the server default for new rows only.
-- (Adding DEFAULT now() up-front populates every row with migration time,
--  making the subsequent UPDATE a no-op — BUG 28 fix.)
ALTER TABLE node_labels
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE node_labels
SET updated_at = COALESCE(created_at, now())
WHERE updated_at IS NULL;

ALTER TABLE node_labels
  ALTER COLUMN updated_at SET DEFAULT now();

CREATE TABLE IF NOT EXISTS node_label_revisions (
  id SERIAL PRIMARY KEY,
  node_label_id INT NOT NULL REFERENCES node_labels(id) ON DELETE CASCADE,
  node_id INT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
  labels JSONB NOT NULL DEFAULT '[]'::jsonb,
  annotator VARCHAR(200) NOT NULL DEFAULT 'default',
  source VARCHAR(50) NOT NULL DEFAULT 'human',
  version INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_node_label_revisions_node_label_id
  ON node_label_revisions (node_label_id);

CREATE INDEX IF NOT EXISTS idx_node_label_revisions_node_id
  ON node_label_revisions (node_id);

CREATE INDEX IF NOT EXISTS idx_node_label_revisions_node_annotator
  ON node_label_revisions (node_id, annotator, version);

-- Prevents duplicate revision rows from concurrent set_node_labels calls
-- (matches the UniqueConstraint in NodeLabelRevision SQLAlchemy model).
ALTER TABLE node_label_revisions
  DROP CONSTRAINT IF EXISTS uq_node_label_revision_version;
ALTER TABLE node_label_revisions
  ADD CONSTRAINT uq_node_label_revision_version
  UNIQUE (node_label_id, version);

INSERT INTO node_label_revisions (node_label_id, node_id, labels, annotator, source, version, created_at)
SELECT nl.id, nl.node_id, nl.labels, nl.annotator, nl.source, COALESCE(nl.version, 1), COALESCE(nl.created_at, now())
FROM node_labels nl
WHERE NOT EXISTS (
  SELECT 1
  FROM node_label_revisions r
  WHERE r.node_label_id = nl.id
    AND r.version = COALESCE(nl.version, 1)
);
