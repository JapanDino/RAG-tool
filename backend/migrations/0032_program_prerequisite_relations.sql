ALTER TABLE competencies
  ADD CONSTRAINT ux_competencies_program_id_id UNIQUE (program_id, id);

CREATE TABLE program_prerequisite_relations (
  id SERIAL PRIMARY KEY,
  program_id INT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  prerequisite_competency_id INT NOT NULL,
  target_competency_id INT NOT NULL,
  rationale TEXT NOT NULL,
  created_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  updated_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ux_program_prerequisites_directed_pair
    UNIQUE (program_id, prerequisite_competency_id, target_competency_id),
  CONSTRAINT fk_program_prerequisites_prerequisite
    FOREIGN KEY (program_id, prerequisite_competency_id)
    REFERENCES competencies(program_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_program_prerequisites_target
    FOREIGN KEY (program_id, target_competency_id)
    REFERENCES competencies(program_id, id) ON DELETE CASCADE,
  CONSTRAINT ck_program_prerequisites_not_self
    CHECK (prerequisite_competency_id <> target_competency_id)
);

CREATE INDEX ix_program_prerequisites_program_id
  ON program_prerequisite_relations(program_id);
CREATE INDEX ix_program_prerequisites_prerequisite_competency_id
  ON program_prerequisite_relations(prerequisite_competency_id);
CREATE INDEX ix_program_prerequisites_target_competency_id
  ON program_prerequisite_relations(target_competency_id);
CREATE INDEX ix_program_prerequisites_created_by_user_id
  ON program_prerequisite_relations(created_by_user_id);
CREATE INDEX ix_program_prerequisites_updated_by_user_id
  ON program_prerequisite_relations(updated_by_user_id);
