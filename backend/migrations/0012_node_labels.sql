CREATE TABLE IF NOT EXISTS node_labels (
  id SERIAL PRIMARY KEY,
  node_id INT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
  labels JSONB NOT NULL DEFAULT '[]'::jsonb,
  annotator VARCHAR(200) NOT NULL DEFAULT 'default',
  source VARCHAR(50) NOT NULL DEFAULT 'human',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_node_labels_node_annotator
  ON node_labels (node_id, annotator);

CREATE INDEX IF NOT EXISTS idx_node_labels_node_id ON node_labels (node_id);

