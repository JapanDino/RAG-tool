CREATE TABLE IF NOT EXISTS courses (
  id SERIAL PRIMARY KEY,
  dataset_id INT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  external_id VARCHAR(255), title VARCHAR(500) NOT NULL,
  description TEXT NOT NULL DEFAULT '', source_type VARCHAR(50) NOT NULL DEFAULT 'manual',
  source_url VARCHAR(2000), source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT ux_courses_dataset_id UNIQUE (dataset_id)
);
CREATE INDEX IF NOT EXISTS idx_courses_external_id ON courses(external_id);
CREATE INDEX IF NOT EXISTS idx_courses_source_type ON courses(source_type);

CREATE TABLE IF NOT EXISTS course_modules (
  id SERIAL PRIMARY KEY, course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  external_id VARCHAR(255), title VARCHAR(500) NOT NULL, description TEXT NOT NULL DEFAULT '',
  position INT NOT NULL DEFAULT 0, source_url VARCHAR(2000), metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT ux_course_modules_external UNIQUE (course_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_course_modules_course ON course_modules(course_id, position);

CREATE TABLE IF NOT EXISTS audit_runs (
  id SERIAL PRIMARY KEY, course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  status VARCHAR(50) NOT NULL DEFAULT 'queued', pipeline_version VARCHAR(100) NOT NULL DEFAULT 'course-audit-v1',
  extractor_version VARCHAR(100) NOT NULL DEFAULT 'objective-baseline-v1',
  classifier_version VARCHAR(100) NOT NULL DEFAULT 'bloom-keyword-v1',
  embedding_model VARCHAR(200) NOT NULL DEFAULT '', relation_model VARCHAR(200) NOT NULL DEFAULT 'hybrid-baseline-v1',
  config JSONB NOT NULL DEFAULT '{}'::jsonb, metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT, created_at TIMESTAMPTZ DEFAULT now(), finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_audit_runs_course_created ON audit_runs(course_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_runs_status ON audit_runs(status);

CREATE TABLE IF NOT EXISTS learning_objectives (
  id SERIAL PRIMARY KEY, course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  module_id INT REFERENCES course_modules(id) ON DELETE SET NULL, document_id INT REFERENCES documents(id) ON DELETE SET NULL,
  audit_run_id INT REFERENCES audit_runs(id) ON DELETE CASCADE, text TEXT NOT NULL, normalized_text TEXT NOT NULL DEFAULT '',
  bloom_vector JSONB NOT NULL DEFAULT '[]'::jsonb, top_bloom_levels JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_start INT, source_end INT, source_page INT, extraction_method VARCHAR(100) NOT NULL DEFAULT 'baseline',
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0, model_info JSONB NOT NULL DEFAULT '{}'::jsonb,
  review_status VARCHAR(50) NOT NULL DEFAULT 'unreviewed'
);
CREATE INDEX IF NOT EXISTS idx_learning_objectives_course_run ON learning_objectives(course_id, audit_run_id);
CREATE INDEX IF NOT EXISTS idx_learning_objectives_module ON learning_objectives(module_id);

CREATE TABLE IF NOT EXISTS learning_materials (
  id SERIAL PRIMARY KEY, course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  module_id INT REFERENCES course_modules(id) ON DELETE SET NULL, document_id INT REFERENCES documents(id) ON DELETE SET NULL,
  audit_run_id INT REFERENCES audit_runs(id) ON DELETE CASCADE, material_type VARCHAR(50) NOT NULL DEFAULT 'other',
  title VARCHAR(500) NOT NULL, source_url VARCHAR(2000), source_text TEXT NOT NULL DEFAULT '',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_learning_materials_course_run ON learning_materials(course_id, audit_run_id);
CREATE INDEX IF NOT EXISTS idx_learning_materials_module ON learning_materials(module_id);

CREATE TABLE IF NOT EXISTS assessment_items (
  id SERIAL PRIMARY KEY, course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  module_id INT REFERENCES course_modules(id) ON DELETE SET NULL, document_id INT REFERENCES documents(id) ON DELETE SET NULL,
  audit_run_id INT REFERENCES audit_runs(id) ON DELETE CASCADE, external_id VARCHAR(255),
  assessment_type VARCHAR(50) NOT NULL DEFAULT 'other', title VARCHAR(500) NOT NULL DEFAULT '', text TEXT NOT NULL,
  expected_answer TEXT, bloom_vector JSONB NOT NULL DEFAULT '[]'::jsonb,
  top_bloom_levels JSONB NOT NULL DEFAULT '[]'::jsonb, source_start INT, source_end INT, source_page INT,
  extraction_method VARCHAR(100) NOT NULL DEFAULT 'baseline', confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  model_info JSONB NOT NULL DEFAULT '{}'::jsonb, review_status VARCHAR(50) NOT NULL DEFAULT 'unreviewed'
);
CREATE INDEX IF NOT EXISTS idx_assessment_items_course_run ON assessment_items(course_id, audit_run_id);
CREATE INDEX IF NOT EXISTS idx_assessment_items_module ON assessment_items(module_id);

CREATE TABLE IF NOT EXISTS alignment_edges (
  id SERIAL PRIMARY KEY, course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  audit_run_id INT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
  source_type VARCHAR(50) NOT NULL, source_id INT NOT NULL, target_type VARCHAR(50) NOT NULL, target_id INT NOT NULL,
  relation_type VARCHAR(50) NOT NULL, score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  evidence JSONB NOT NULL DEFAULT '[]'::jsonb, method VARCHAR(100) NOT NULL DEFAULT 'hybrid-baseline-v1',
  model_info JSONB NOT NULL DEFAULT '{}'::jsonb, review_status VARCHAR(50) NOT NULL DEFAULT 'unreviewed',
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT ux_alignment_edges_run_relation UNIQUE
    (audit_run_id, source_type, source_id, target_type, target_id, relation_type),
  CONSTRAINT ck_alignment_edges_score CHECK (score >= 0.0 AND score <= 1.0)
);
CREATE INDEX IF NOT EXISTS idx_alignment_edges_course_run ON alignment_edges(course_id, audit_run_id);
CREATE INDEX IF NOT EXISTS idx_alignment_edges_relation ON alignment_edges(relation_type);

CREATE TABLE IF NOT EXISTS course_findings (
  id SERIAL PRIMARY KEY, course_id INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  module_id INT REFERENCES course_modules(id) ON DELETE SET NULL,
  audit_run_id INT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
  finding_type VARCHAR(100) NOT NULL, severity VARCHAR(20) NOT NULL DEFAULT 'medium',
  title VARCHAR(500) NOT NULL, description TEXT NOT NULL, evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  recommendation TEXT NOT NULL DEFAULT '', confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  uncertainty_reasons JSONB NOT NULL DEFAULT '[]'::jsonb, status VARCHAR(50) NOT NULL DEFAULT 'new',
  reviewed_by VARCHAR(255), reviewed_at TIMESTAMPTZ, model_info JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT ck_course_findings_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);
CREATE INDEX IF NOT EXISTS idx_course_findings_course_run ON course_findings(course_id, audit_run_id);
CREATE INDEX IF NOT EXISTS idx_course_findings_status ON course_findings(status);
CREATE INDEX IF NOT EXISTS idx_course_findings_type ON course_findings(finding_type);
