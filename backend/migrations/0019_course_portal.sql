CREATE TABLE IF NOT EXISTS portal_courses (
    id SERIAL PRIMARY KEY,
    binding VARCHAR(64) NOT NULL UNIQUE,
    canvas_course_id INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    dataset_id INTEGER NOT NULL UNIQUE REFERENCES datasets(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS portal_materials (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    source_url TEXT,
    source_ref TEXT,
    source_hash VARCHAR(64),
    kind VARCHAR(30) NOT NULL DEFAULT 'literature'
);
CREATE INDEX IF NOT EXISTS ix_portal_material_course ON portal_materials(course_id);
CREATE TABLE IF NOT EXISTS portal_feedback (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    rating VARCHAR(20) NOT NULL CHECK (rating IN ('clear','difficult','error')),
    comment VARCHAR(2000) NOT NULL DEFAULT '',
    day DATE NOT NULL DEFAULT CURRENT_DATE
);
CREATE TABLE IF NOT EXISTS portal_metrics (
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    day DATE NOT NULL DEFAULT CURRENT_DATE,
    kind VARCHAR(30) NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(course_id, day, kind)
);
