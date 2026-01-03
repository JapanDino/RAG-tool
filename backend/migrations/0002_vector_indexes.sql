-- Дополнительные индексы для ускорения поиска
-- Требуется pgvector >= 0.6.0 (HNSW доступен)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_embeddings_vec_hnsw'
  ) THEN
    CREATE INDEX idx_embeddings_vec_hnsw ON embeddings USING hnsw (vec) WITH (m = 16, ef_construction = 200);
  END IF;
END$$;
