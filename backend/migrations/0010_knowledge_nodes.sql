CREATE TABLE IF NOT EXISTS knowledge_nodes (
  id SERIAL PRIMARY KEY,
  dataset_id INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  document_id INT REFERENCES documents(id) ON DELETE SET NULL,
  chunk_id INT REFERENCES chunks(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  context_text TEXT NOT NULL,
  prob_vector JSONB NOT NULL DEFAULT '[]'::jsonb,
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
DO $$
BEGIN
  BEGIN
    IF EXISTS (
      SELECT 1
      FROM pg_indexes
      WHERE schemaname = 'public'
        AND indexname = 'idx_knowledge_nodes_vec'
    ) THEN
      NULL;
    ELSE
      SET LOCAL maintenance_work_mem = '256MB';
      CREATE INDEX idx_knowledge_nodes_vec ON knowledge_nodes USING ivfflat (vec vector_l2_ops) WITH (lists = 100);
    END IF;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping initial knowledge_nodes vector index creation: %', SQLERRM;
  END;
END$$;
