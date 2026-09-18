CREATE TABLE IF NOT EXISTS organizations (
  id SERIAL PRIMARY KEY,
  slug VARCHAR(120) NOT NULL UNIQUE,
  name VARCHAR(300) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS ix_organizations_is_active ON organizations(is_active);

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(320) NOT NULL UNIQUE,
  display_name VARCHAR(300) NOT NULL,
  external_subject VARCHAR(500) UNIQUE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_external_subject ON users(external_subject);
CREATE INDEX IF NOT EXISTS ix_users_is_active ON users(is_active);

CREATE TABLE IF NOT EXISTS organization_memberships (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_organization_memberships_user UNIQUE (organization_id, user_id),
  CONSTRAINT ck_organization_memberships_role CHECK (
    role IN ('student', 'instructor', 'methodologist', 'program_designer', 'administrator')
  )
);
CREATE INDEX IF NOT EXISTS ix_organization_memberships_organization_id
  ON organization_memberships(organization_id);
CREATE INDEX IF NOT EXISTS ix_organization_memberships_user_id
  ON organization_memberships(user_id);
CREATE INDEX IF NOT EXISTS ix_organization_memberships_role
  ON organization_memberships(role);

ALTER TABLE courses
  ADD COLUMN IF NOT EXISTS organization_id INT REFERENCES organizations(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS ix_courses_organization_id ON courses(organization_id);

CREATE TABLE IF NOT EXISTS course_memberships (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_course_memberships_user UNIQUE (course_id, user_id),
  CONSTRAINT ck_course_memberships_role CHECK (
    role IN ('student', 'instructor', 'methodologist', 'program_designer', 'administrator')
  )
);
CREATE INDEX IF NOT EXISTS ix_course_memberships_organization_id
  ON course_memberships(organization_id);
CREATE INDEX IF NOT EXISTS ix_course_memberships_course_id ON course_memberships(course_id);
CREATE INDEX IF NOT EXISTS ix_course_memberships_user_id ON course_memberships(user_id);
CREATE INDEX IF NOT EXISTS ix_course_memberships_role ON course_memberships(role);

CREATE TABLE IF NOT EXISTS membership_audit_events (
  id SERIAL PRIMARY KEY,
  organization_id INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  target_user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type VARCHAR(50) NOT NULL,
  previous_role VARCHAR(50),
  new_role VARCHAR(50),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_membership_audit_events_organization_id
  ON membership_audit_events(organization_id);
CREATE INDEX IF NOT EXISTS ix_membership_audit_events_course_id
  ON membership_audit_events(course_id);
CREATE INDEX IF NOT EXISTS ix_membership_audit_events_actor_user_id
  ON membership_audit_events(actor_user_id);
CREATE INDEX IF NOT EXISTS ix_membership_audit_events_target_user_id
  ON membership_audit_events(target_user_id);
CREATE INDEX IF NOT EXISTS ix_membership_audit_events_event_type
  ON membership_audit_events(event_type);
