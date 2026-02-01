CREATE TABLE IF NOT EXISTS knowledge_nodes (
  id SERIAL PRIMARY KEY,
  dataset_id INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  document_id INT REFERENCES documents(id) ON DELETE SET NULL,
  chunk_id INT REFERENCES chunks(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  context_text TEXT NOT NULL,
  prob_vector JSONB NOT NULL DEFAULT '{}'::jsonb,
  top_levels JSONB NOT NULL DEFAULT '[]'::jsonb,
  embedding_dim INT NOT NULL DEFAULT 1536,
  embedding_model VARCHAR(100) DEFAULT 'text-embedding-3-small',
  vec vector(1536),
  version INT NOT NULL DEFAULT 1,
  model_info JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_dataset_id ON knowledge_nodes (dataset_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_document_id ON knowledge_nodes (document_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_chunk_id ON knowledge_nodes (chunk_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_vec ON knowledge_nodes USING ivfflat (vec) WITH (lists = 100);
