CREATE TABLE IF NOT EXISTS portal_bloom_reviews (
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    text_hash VARCHAR(64) NOT NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('confirmed','corrected','needs_context')),
    levels JSONB NOT NULL,
    knowledge JSONB NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    automatic JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (course_id,document_id,text_hash)
);
CREATE TABLE IF NOT EXISTS portal_preview_checks (
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content_hash VARCHAR(64) NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(course_id,document_id)
);
CREATE TABLE IF NOT EXISTS portal_study_sessions (
    id UUID PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES portal_courses(id) ON DELETE CASCADE,
    owner VARCHAR(64) NOT NULL,
    scope_document INTEGER NOT NULL DEFAULT 0,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);
CREATE INDEX IF NOT EXISTS ix_portal_study_owner ON portal_study_sessions(course_id,owner,scope_document,updated_at);
