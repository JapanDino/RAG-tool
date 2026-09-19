CREATE TABLE IF NOT EXISTS portal_settings (
    course_id INTEGER PRIMARY KEY REFERENCES portal_courses(id) ON DELETE CASCADE,
    quality_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    allow_solutions BOOLEAN NOT NULL DEFAULT FALSE,
    solution_after_attempts INTEGER NOT NULL DEFAULT 2 CHECK (solution_after_attempts BETWEEN 1 AND 5)
);
CREATE TABLE IF NOT EXISTS portal_quality (
    id UUID PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    day DATE NOT NULL DEFAULT CURRENT_DATE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    document_ids JSONB NOT NULL DEFAULT '[]',
    feedback VARCHAR(20),
    feedback_key VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved'))
);
CREATE INDEX IF NOT EXISTS ix_portal_quality_course ON portal_quality(course_id,day);
CREATE TABLE IF NOT EXISTS portal_imports (
    id UUID PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_portal_imports_course ON portal_imports(course_id,updated_at);
ALTER TABLE portal_materials ADD COLUMN IF NOT EXISTS module_name TEXT;
ALTER TABLE portal_materials ADD COLUMN IF NOT EXISTS module_position INTEGER;
ALTER TABLE portal_materials ADD COLUMN IF NOT EXISTS item_position INTEGER;
ALTER TABLE portal_materials ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ;
ALTER TABLE portal_materials ADD COLUMN IF NOT EXISTS unavailable_reason TEXT;
ALTER TABLE portal_materials ADD COLUMN IF NOT EXISTS module_refs JSONB NOT NULL DEFAULT '[]';
