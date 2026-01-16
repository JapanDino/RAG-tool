ALTER TABLE bloom_annotations
  ADD COLUMN IF NOT EXISTS rubric_id INT REFERENCES rubrics(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_bloom_annotations_rubric_id
  ON bloom_annotations (rubric_id);

