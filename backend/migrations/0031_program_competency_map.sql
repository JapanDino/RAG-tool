CREATE TABLE IF NOT EXISTS programs (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  code VARCHAR(80) NOT NULL,
  title VARCHAR(500) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  version INT NOT NULL DEFAULT 1,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_programs_org_code UNIQUE (organization_id, code),
  CONSTRAINT ck_programs_version CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS ix_programs_organization_id
  ON programs(organization_id);
CREATE INDEX IF NOT EXISTS ix_programs_is_active
  ON programs(is_active);
CREATE INDEX IF NOT EXISTS ix_programs_created_by_user_id
  ON programs(created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_programs_updated_by_user_id
  ON programs(updated_by_user_id);

CREATE TABLE IF NOT EXISTS program_courses (
  id SERIAL PRIMARY KEY,
  program_id INT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  position INT NOT NULL,
  added_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_program_courses_program_course UNIQUE (program_id, course_id),
  CONSTRAINT ux_program_courses_program_position UNIQUE (program_id, position),
  CONSTRAINT ck_program_courses_position CHECK (position > 0)
);

CREATE INDEX IF NOT EXISTS ix_program_courses_program_id
  ON program_courses(program_id);
CREATE INDEX IF NOT EXISTS ix_program_courses_course_id
  ON program_courses(course_id);
CREATE INDEX IF NOT EXISTS ix_program_courses_added_by_user_id
  ON program_courses(added_by_user_id);

CREATE TABLE IF NOT EXISTS competencies (
  id SERIAL PRIMARY KEY,
  program_id INT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  code VARCHAR(80) NOT NULL,
  title VARCHAR(500) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  position INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_competencies_program_code UNIQUE (program_id, code),
  CONSTRAINT ck_competencies_position CHECK (position >= 0)
);

CREATE INDEX IF NOT EXISTS ix_competencies_program_id
  ON competencies(program_id);

CREATE TABLE IF NOT EXISTS course_contributions (
  id SERIAL PRIMARY KEY,
  program_id INT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  competency_id INT NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  stage VARCHAR(50) NOT NULL,
  rationale TEXT NOT NULL,
  evidence_type VARCHAR(50) NOT NULL,
  evidence_id INT,
  created_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_course_contributions_competency_course
    UNIQUE (competency_id, course_id),
  CONSTRAINT fk_course_contributions_program_course
    FOREIGN KEY (program_id, course_id)
    REFERENCES program_courses(program_id, course_id) ON DELETE CASCADE,
  CONSTRAINT ck_course_contributions_stage
    CHECK (stage IN ('introduced', 'developed', 'assessed')),
  CONSTRAINT ck_course_contributions_evidence_type
    CHECK (evidence_type IN ('learning_objective', 'assessment_item', 'manual_note')),
  CONSTRAINT ck_course_contributions_evidence_reference
    CHECK (
      (evidence_type = 'manual_note' AND evidence_id IS NULL)
      OR (evidence_type <> 'manual_note' AND evidence_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_course_contributions_program_id
  ON course_contributions(program_id);
CREATE INDEX IF NOT EXISTS ix_course_contributions_competency_id
  ON course_contributions(competency_id);
CREATE INDEX IF NOT EXISTS ix_course_contributions_course_id
  ON course_contributions(course_id);
CREATE INDEX IF NOT EXISTS ix_course_contributions_stage
  ON course_contributions(stage);
CREATE INDEX IF NOT EXISTS ix_course_contributions_evidence_type
  ON course_contributions(evidence_type);
CREATE INDEX IF NOT EXISTS ix_course_contributions_created_by_user_id
  ON course_contributions(created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_course_contributions_updated_by_user_id
  ON course_contributions(updated_by_user_id);

CREATE TABLE IF NOT EXISTS program_change_events (
  id SERIAL PRIMARY KEY,
  program_id INT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  event_type VARCHAR(80) NOT NULL,
  entity_type VARCHAR(80) NOT NULL,
  entity_id INT,
  version INT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_program_change_events_version CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS ix_program_change_events_program_id
  ON program_change_events(program_id);
CREATE INDEX IF NOT EXISTS ix_program_change_events_organization_id
  ON program_change_events(organization_id);
CREATE INDEX IF NOT EXISTS ix_program_change_events_actor_user_id
  ON program_change_events(actor_user_id);
CREATE INDEX IF NOT EXISTS ix_program_change_events_event_type
  ON program_change_events(event_type);
