-- Align ANN indexes and upsert constraints with the current retrieval logic.

SET maintenance_work_mem = '256MB';

CREATE UNIQUE INDEX IF NOT EXISTS ux_embeddings_chunk_id
  ON embeddings (chunk_id);

DO $$
BEGIN
  BEGIN
    IF EXISTS (
      SELECT 1
      FROM pg_indexes
      WHERE schemaname = 'public'
        AND indexname = 'idx_embeddings_vec'
        AND indexdef NOT LIKE '%vector_cosine_ops%'
    ) THEN
      DROP INDEX idx_embeddings_vec;
    END IF;
    CREATE INDEX IF NOT EXISTS idx_embeddings_vec
      ON embeddings USING ivfflat (vec vector_cosine_ops) WITH (lists = 100);
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping embeddings cosine IVFFLAT index creation: %', SQLERRM;
  END;
END$$;

DO $$
BEGIN
  BEGIN
    IF EXISTS (
      SELECT 1
      FROM pg_indexes
      WHERE schemaname = 'public'
        AND indexname = 'idx_embeddings_vec_hnsw'
    ) THEN
      NULL;
    ELSE
      CREATE INDEX idx_embeddings_vec_hnsw ON embeddings USING hnsw (vec vector_cosine_ops)
        WITH (m = 16, ef_construction = 200);
    END IF;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping HNSW cosine index creation: %', SQLERRM;
  END;
END$$;

DO $$
BEGIN
  BEGIN
    IF EXISTS (
      SELECT 1
      FROM pg_indexes
      WHERE schemaname = 'public'
        AND indexname = 'idx_knowledge_nodes_vec'
        AND indexdef NOT LIKE '%vector_cosine_ops%'
    ) THEN
      DROP INDEX idx_knowledge_nodes_vec;
    END IF;
    CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_vec
      ON knowledge_nodes USING ivfflat (vec vector_cosine_ops) WITH (lists = 100);
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping knowledge_nodes cosine IVFFLAT index creation: %', SQLERRM;
  END;
END$$;

RESET maintenance_work_mem;
