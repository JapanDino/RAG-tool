CREATE TABLE IF NOT EXISTS course_intervention_drafts (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    source_dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    source_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    source_audit_run_id INTEGER REFERENCES audit_runs(id) ON DELETE SET NULL,
    aggregate_digest VARCHAR(64) NOT NULL,
    signal_kind VARCHAR(40) NOT NULL,
    cohort_band VARCHAR(20) NOT NULL,
    event_band VARCHAR(20) NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    window_ended_at TIMESTAMPTZ NOT NULL,
    title VARCHAR(500) NOT NULL,
    initial_content TEXT NOT NULL,
    content TEXT NOT NULL,
    rationale TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    version INTEGER NOT NULL DEFAULT 1,
    reviewed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    review_reason VARCHAR(50),
    edit_distance_ratio DOUBLE PRECISION,
    decision_latency_seconds INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_course_intervention_drafts_signal_kind
        CHECK (signal_kind IN ('repeated_unsupported', 'low_helpfulness', 'mixed')),
    CONSTRAINT ck_course_intervention_drafts_status
        CHECK (status IN ('draft', 'accepted', 'rejected')),
    CONSTRAINT ck_course_intervention_drafts_version_positive CHECK (version >= 1)
);

CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_course_id
    ON course_intervention_drafts(course_id);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_source_dataset_id
    ON course_intervention_drafts(source_dataset_id);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_source_document_id
    ON course_intervention_drafts(source_document_id);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_source_chunk_id
    ON course_intervention_drafts(source_chunk_id);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_source_audit_run_id
    ON course_intervention_drafts(source_audit_run_id);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_aggregate_digest
    ON course_intervention_drafts(aggregate_digest);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_signal_kind
    ON course_intervention_drafts(signal_kind);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_status
    ON course_intervention_drafts(status);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_reviewed_by_user_id
    ON course_intervention_drafts(reviewed_by_user_id);
CREATE INDEX IF NOT EXISTS ix_course_intervention_drafts_review_reason
    ON course_intervention_drafts(review_reason);
