-- Align ANN indexes and upsert constraints with the current retrieval logic.

CREATE UNIQUE INDEX IF NOT EXISTS ux_embeddings_chunk_id
  ON embeddings (chunk_id);

DROP INDEX IF EXISTS idx_embeddings_vec;
CREATE INDEX IF NOT EXISTS idx_embeddings_vec
  ON embeddings USING ivfflat (vec vector_cosine_ops) WITH (lists = 100);

DROP INDEX IF EXISTS idx_embeddings_vec_hnsw;
DO $$
BEGIN
  BEGIN
    CREATE INDEX idx_embeddings_vec_hnsw ON embeddings USING hnsw (vec vector_cosine_ops)
      WITH (m = 16, ef_construction = 200);
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping HNSW cosine index creation: %', SQLERRM;
  END;
END$$;

DROP INDEX IF EXISTS idx_knowledge_nodes_vec;
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_vec
  ON knowledge_nodes USING ivfflat (vec vector_cosine_ops) WITH (lists = 100);
