-- Уникальный эмбеддинг на chunk_id
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ux_embeddings_chunk'
  ) THEN
    CREATE UNIQUE INDEX ux_embeddings_chunk ON embeddings (chunk_id);
  END IF;
END$$;

-- Полезные индексы по FK и сортировкам
CREATE INDEX IF NOT EXISTS ix_documents_dataset_id ON documents (dataset_id);
CREATE INDEX IF NOT EXISTS ix_chunks_document_id_idx ON chunks (document_id, idx);
CREATE INDEX IF NOT EXISTS ix_annotations_chunk_created ON bloom_annotations (chunk_id, created_at);

-- На всякий случай: ограничение score в [0,1]
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'chk_bloom_score_range'
      AND table_name = 'bloom_annotations'
  ) THEN
    ALTER TABLE bloom_annotations
      ADD CONSTRAINT chk_bloom_score_range CHECK (score >= 0 AND score <= 1);
  END IF;
END$$;
