ALTER TABLE node_labels
  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;

ALTER TABLE node_labels
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

UPDATE node_labels
SET updated_at = COALESCE(updated_at, created_at, now());

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

INSERT INTO node_label_revisions (node_label_id, node_id, labels, annotator, source, version, created_at)
SELECT nl.id, nl.node_id, nl.labels, nl.annotator, nl.source, COALESCE(nl.version, 1), COALESCE(nl.created_at, now())
FROM node_labels nl
WHERE NOT EXISTS (
  SELECT 1
  FROM node_label_revisions r
  WHERE r.node_label_id = nl.id
    AND r.version = COALESCE(nl.version, 1)
);
