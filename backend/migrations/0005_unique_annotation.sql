CREATE UNIQUE INDEX IF NOT EXISTS ux_bloom_annotations_chunk_level
  ON bloom_annotations (chunk_id, level);

