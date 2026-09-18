CREATE TABLE IF NOT EXISTS organization_tutor_data_policies (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  retention_days INT NOT NULL DEFAULT 90,
  version INT NOT NULL DEFAULT 1,
  updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_organization_tutor_data_policies_org UNIQUE (organization_id),
  CONSTRAINT ck_organization_tutor_data_policies_days
    CHECK (retention_days IN (30, 90, 180, 365))
);

CREATE INDEX IF NOT EXISTS ix_organization_tutor_data_policies_organization_id
  ON organization_tutor_data_policies(organization_id);
CREATE INDEX IF NOT EXISTS ix_organization_tutor_data_policies_updated_by_user_id
  ON organization_tutor_data_policies(updated_by_user_id);

CREATE TABLE IF NOT EXISTS organization_tutor_data_policy_events (
  id SERIAL PRIMARY KEY,
  policy_id INT NOT NULL REFERENCES organization_tutor_data_policies(id) ON DELETE CASCADE,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  previous_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  new_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  version INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_organization_tutor_data_policy_events_policy_id
  ON organization_tutor_data_policy_events(policy_id);
CREATE INDEX IF NOT EXISTS ix_organization_tutor_data_policy_events_organization_id
  ON organization_tutor_data_policy_events(organization_id);
CREATE INDEX IF NOT EXISTS ix_organization_tutor_data_policy_events_actor_user_id
  ON organization_tutor_data_policy_events(actor_user_id);

CREATE TABLE IF NOT EXISTS tutor_data_deletion_events (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  course_id INT REFERENCES courses(id) ON DELETE SET NULL,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  subject_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  reason VARCHAR(50) NOT NULL,
  policy_version INT NOT NULL DEFAULT 0,
  cutoff TIMESTAMPTZ,
  answers_deleted INT NOT NULL DEFAULT 0,
  feedback_events_deleted INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_tutor_data_deletion_events_reason
    CHECK (reason IN ('student_request', 'automatic_retention', 'admin_purge')),
  CONSTRAINT ck_tutor_data_deletion_events_counts
    CHECK (answers_deleted >= 0 AND feedback_events_deleted >= 0)
);

CREATE INDEX IF NOT EXISTS ix_tutor_data_deletion_events_organization_id
  ON tutor_data_deletion_events(organization_id);
CREATE INDEX IF NOT EXISTS ix_tutor_data_deletion_events_course_id
  ON tutor_data_deletion_events(course_id);
CREATE INDEX IF NOT EXISTS ix_tutor_data_deletion_events_actor_user_id
  ON tutor_data_deletion_events(actor_user_id);
CREATE INDEX IF NOT EXISTS ix_tutor_data_deletion_events_subject_user_id
  ON tutor_data_deletion_events(subject_user_id);
CREATE INDEX IF NOT EXISTS ix_tutor_data_deletion_events_reason
  ON tutor_data_deletion_events(reason);
