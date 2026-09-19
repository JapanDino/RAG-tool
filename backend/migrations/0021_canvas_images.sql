ALTER TABLE portal_images ADD COLUMN IF NOT EXISTS canvas_file_id BIGINT;
ALTER TABLE portal_images ADD COLUMN IF NOT EXISTS canvas_file_version TEXT;
-- Prefix distinguishes full HTML fingerprints from legacy text-only page hashes.
ALTER TABLE portal_materials ALTER COLUMN source_hash TYPE TEXT;
