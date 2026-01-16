INSERT INTO rubrics (level, name, description, criteria, version, is_active)
SELECT 'remember', 'Remember', 'Определите/назовите/воспроизведите ключевые факты.', '{}'::jsonb, 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM rubrics WHERE level = 'remember' AND is_active = TRUE);

INSERT INTO rubrics (level, name, description, criteria, version, is_active)
SELECT 'understand', 'Understand', 'Переформулируйте и объясните идею своими словами.', '{}'::jsonb, 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM rubrics WHERE level = 'understand' AND is_active = TRUE);

INSERT INTO rubrics (level, name, description, criteria, version, is_active)
SELECT 'apply', 'Apply', 'Примените метод к типовой задаче.', '{}'::jsonb, 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM rubrics WHERE level = 'apply' AND is_active = TRUE);

INSERT INTO rubrics (level, name, description, criteria, version, is_active)
SELECT 'analyze', 'Analyze', 'Разбейте на части, выделите зависимости/причины.', '{}'::jsonb, 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM rubrics WHERE level = 'analyze' AND is_active = TRUE);

INSERT INTO rubrics (level, name, description, criteria, version, is_active)
SELECT 'evaluate', 'Evaluate', 'Сравните подходы, сформулируйте критерии и вывод.', '{}'::jsonb, 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM rubrics WHERE level = 'evaluate' AND is_active = TRUE);

INSERT INTO rubrics (level, name, description, criteria, version, is_active)
SELECT 'create', 'Create', 'Синтезируйте новое решение/план/вариант.', '{}'::jsonb, 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM rubrics WHERE level = 'create' AND is_active = TRUE);

