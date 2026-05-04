-- Fix 1: Replace the L2-ops HNSW on embeddings (created by 0002) with cosine-ops HNSW.
--         0015 only creates the cosine HNSW if idx_embeddings_vec_hnsw does NOT exist,
--         so a DB that applied 0002 before 0015 is left with the wrong operator class.
-- Fix 2: Add HNSW on knowledge_nodes.vec (0015 created IVFFlat there, not HNSW).

SET maintenance_work_mem = '512MB';

DO $$
BEGIN
  -- Drop old L2-ops HNSW on embeddings so we can recreate with cosine ops.
  IF EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'idx_embeddings_vec_hnsw'
      AND indexdef LIKE '%vector_l2_ops%'
  ) THEN
    DROP INDEX idx_embeddings_vec_hnsw;
    RAISE NOTICE '0017: dropped L2-ops HNSW on embeddings, will recreate with cosine ops';
  END IF;

  BEGIN
    CREATE INDEX IF NOT EXISTS idx_embeddings_vec_hnsw
      ON embeddings USING hnsw (vec vector_cosine_ops)
      WITH (m = 16, ef_construction = 200);
    RAISE NOTICE '0017: HNSW cosine index on embeddings ensured';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE '0017: could not create HNSW on embeddings: %', SQLERRM;
  END;
END$$;

DO $$
BEGIN
  BEGIN
    -- Drop IVFFlat on knowledge_nodes if it used L2 ops (legacy)
    IF EXISTS (
      SELECT 1 FROM pg_indexes
      WHERE schemaname = 'public'
        AND indexname = 'idx_knowledge_nodes_vec'
        AND indexdef LIKE '%vector_l2_ops%'
    ) THEN
      DROP INDEX idx_knowledge_nodes_vec;
    END IF;

    -- Create HNSW on knowledge_nodes.vec with cosine ops (model declares ix_knode_vec_hnsw)
    CREATE INDEX IF NOT EXISTS ix_knode_vec_hnsw
      ON knowledge_nodes USING hnsw (vec vector_cosine_ops)
      WITH (m = 16, ef_construction = 64);
    RAISE NOTICE '0017: HNSW cosine index on knowledge_nodes ensured';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE '0017: could not create HNSW on knowledge_nodes: %', SQLERRM;
  END;
END$$;

RESET maintenance_work_mem;
