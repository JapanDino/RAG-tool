CREATE TABLE IF NOT EXISTS portal_files (
    document_id INTEGER PRIMARY KEY REFERENCES portal_materials(document_id) ON DELETE CASCADE,
    mime TEXT NOT NULL,
    data BYTEA NOT NULL
);
CREATE TABLE IF NOT EXISTS portal_images (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES portal_materials(document_id) ON DELETE CASCADE,
    chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
    caption VARCHAR(500) NOT NULL,
    location VARCHAR(100) NOT NULL,
    page INTEGER,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    data BYTEA NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_portal_images_document ON portal_images(document_id);
CREATE INDEX IF NOT EXISTS ix_portal_images_chunk ON portal_images(chunk_id);
