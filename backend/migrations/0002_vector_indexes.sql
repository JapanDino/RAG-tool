-- Дополнительные индексы для ускорения поиска
-- Требуется pgvector >= 0.6.0 (HNSW доступен)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_embeddings_vec_hnsw'
  ) THEN
    BEGIN
      -- pgvector does not define a default operator class for HNSW; specify explicitly.
      CREATE INDEX idx_embeddings_vec_hnsw ON embeddings USING hnsw (vec vector_l2_ops)
        WITH (m = 16, ef_construction = 200);
    EXCEPTION WHEN OTHERS THEN
      -- If pgvector is too old or HNSW/opclass is unavailable, don't block startup.
      RAISE NOTICE 'Skipping HNSW index creation: %', SQLERRM;
    END;
  END IF;
END$$;
