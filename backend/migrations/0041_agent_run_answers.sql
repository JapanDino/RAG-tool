ALTER TABLE agent_runs
  ADD COLUMN answer_id INT REFERENCES course_question_answers(id) ON DELETE SET NULL;

CREATE INDEX ix_agent_runs_answer_id ON agent_runs(answer_id);
