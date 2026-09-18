CREATE TABLE IF NOT EXISTS program_review_notes (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  program_id INT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  finding_key VARCHAR(160) NOT NULL,
  finding_kind VARCHAR(50) NOT NULL,
  source_digest VARCHAR(64) NOT NULL,
  initial_draft_digest VARCHAR(64) NOT NULL,
  content TEXT NOT NULL,
  decision VARCHAR(20) NOT NULL,
  version INT NOT NULL DEFAULT 1,
  created_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_program_review_notes_program_finding
    UNIQUE (program_id, finding_key),
  CONSTRAINT ck_program_review_notes_decision
    CHECK (decision IN ('act', 'observe', 'dismiss')),
  CONSTRAINT ck_program_review_notes_version CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS ix_program_review_notes_organization_id
  ON program_review_notes(organization_id);
CREATE INDEX IF NOT EXISTS ix_program_review_notes_program_id
  ON program_review_notes(program_id);
CREATE INDEX IF NOT EXISTS ix_program_review_notes_finding_kind
  ON program_review_notes(finding_kind);
CREATE INDEX IF NOT EXISTS ix_program_review_notes_source_digest
  ON program_review_notes(source_digest);
CREATE INDEX IF NOT EXISTS ix_program_review_notes_decision
  ON program_review_notes(decision);
CREATE INDEX IF NOT EXISTS ix_program_review_notes_created_by_user_id
  ON program_review_notes(created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_program_review_notes_updated_by_user_id
  ON program_review_notes(updated_by_user_id);
