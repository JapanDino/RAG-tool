CREATE TABLE IF NOT EXISTS knowledge_edges (
  id SERIAL PRIMARY KEY,
  dataset_id INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  from_node_id INT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
  to_node_id INT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
  weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  method VARCHAR(100) NOT NULL DEFAULT 'vector_topk',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Canonical undirected edges: store (min,max) in (from,to) and dedup by method.
CREATE UNIQUE INDEX IF NOT EXISTS ux_knowledge_edges_dataset_pair_method
  ON knowledge_edges (dataset_id, from_node_id, to_node_id, method);

CREATE INDEX IF NOT EXISTS idx_knowledge_edges_dataset_id ON knowledge_edges (dataset_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_edges_from ON knowledge_edges (from_node_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_edges_to ON knowledge_edges (to_node_id);
