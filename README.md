# Bloom RAG Studio — Course Quality Auditor

Bloom RAG Studio анализирует учебный курс и помогает преподавателю найти конкретные проблемы согласованности:

- цель не обеспечена учебным материалом;
- цель не проверяется заданием;
- когнитивная сложность задания не соответствует уровню цели по таксономии Блума.

Каждый вывод содержит цитаты, ссылки на исходные объекты, confidence, причины неопределённости и рекомендацию. Система не изменяет курс автоматически: преподаватель подтверждает, отклоняет или закрывает finding.

## Основной сценарий

```text
Создать или импортировать курс
→ загрузить цели, материалы и задания
→ запустить асинхронный аудит
→ изучить Overview и Alignment Matrix
→ проверить evidence каждого finding
→ подтвердить, отклонить или отметить проблему исправленной
```

## Архитектура

```text
Next.js UI
   │
FastAPI ── PostgreSQL + pgvector
   │              │
   └── Celery ── Redis
          │
          ├── document classification / extraction
          ├── Bloom multi-label classification
          ├── hybrid alignment
          └── finding detectors
```

Существующий `Dataset` используется как контейнер исходных документов и RAG-индекса. `KnowledgeNode` остаётся сущностью концепта. Педагогические связи хранятся отдельно в `AlignmentEdge`, а каждый запуск анализа версионируется через `AuditRun`.

Ключевые сущности:

- `Course`, `CourseModule`;
- `LearningObjective`, `LearningMaterial`, `AssessmentItem`;
- `AlignmentEdge`, `CourseFinding`;
- `AuditRun`, `FindingReviewEvent`.

## Быстрый запуск

1. Создайте конфигурацию:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

2. Запустите систему:

```powershell
docker compose up --build
```

3. Откройте:

- UI: `http://localhost:3000`;
- OpenAPI: `http://localhost:8000/docs`;
- health/quality status: `http://localhost:8000/health`.

На Windows также доступен `scripts/start-local.ps1`. Подробности находятся в `README_DOCKER_SETUP.md`.

## Переменные окружения

Основные переменные backend:

| Переменная | Назначение |
| --- | --- |
| `DATABASE_URL` | Подключение SQLAlchemy |
| `REDIS_URL` | Broker и result backend Celery |
| `ENABLE_CELERY` | `0` включает синхронный локальный fallback |
| `EMBEDDING_PROVIDER` | `local`, `openai`, `hash`, `random` |
| `BLOOM_CLASSIFIER` | `keyword` или `llm` |
| `NODE_EXTRACTOR` | `semantic`, `local_ner`, `heuristic` |
| `MAX_UPLOAD_BYTES` | Максимальный размер одного файла |
| `MAX_COURSE_DOCUMENTS` | Лимит документов курса |
| `AUTH_MODE` | `development` для локальных ролей; `external` для будущего LTI/OIDC |
| `CORS_ALLOW_ORIGINS` | Разрешённые frontend origins |
| `API_WRITE_KEY` | Опциональная защита mutating endpoints |
| `CANVAS_ALLOWED_HOSTS` | Allow-list Canvas-хостов |

Не храните Canvas token и ключи провайдеров в Git. Canvas token принимается только на время запроса импорта и не сохраняется в БД.

Локальное role-aware пространство доступно по адресу
`http://localhost:3000/workspace`. В режиме `AUTH_MODE=development` оно может
создать демонстрационные профили ученика, преподавателя, методиста, архитектора
программы и администратора. Этот режим автоматически запрещён при
`APP_ENV=production`.

## API: минимальный пример

Создание курса:

```http
POST /courses
Content-Type: application/json

{
  "title": "Алгоритмы и структуры данных",
  "source_type": "manual",
  "modules": [{"title": "Сортировки", "position": 1}]
}
```

Загрузка файла:

```http
POST /courses/{course_id}/documents
Content-Type: multipart/form-data

file=@objectives.txt
document_type=learning_objectives
module_id=1
```

Запуск аудита:

```http
POST /courses/{course_id}/audits
Content-Type: application/json

{"config": {"min_relation_score": 0.22, "top_k": 5}}
```

Результаты:

```text
GET /audits/{audit_run_id}
GET /audits/{audit_run_id}/objectives
GET /audits/{audit_run_id}/assessments
GET /audits/{audit_run_id}/alignment
GET /audits/{audit_run_id}/canvas-alignment
GET /audits/{audit_run_id}/canvas-alignment/calibration
GET /audits/{audit_run_id}/findings
GET /audits/{audit_run_id}/report
PATCH /findings/{finding_id}
POST /courses/{course_id}/qa
GET /courses/{course_id}/qa
GET /courses/{course_id}/canvas-change-set
GET /courses/{course_id}/canvas-change-set/download?format=markdown
PATCH /qa/answers/{answer_id}
GET /qa/answers/{answer_id}/history
GET /courses/{course_id}/ml-feedback
GET /courses/{course_id}/ml-feedback/download
POST /courses/{course_id}/evaluation-protocols
GET /courses/{course_id}/evaluation-protocols
GET /evaluation-protocols/{protocol_id}/download
```

Импорт Canvas:

```http
POST /integrations/canvas/import
Content-Type: application/json

{
  "base_url": "https://canvas.example.edu",
  "canvas_course_id": 42,
  "access_token": "temporary-token"
}
```

Импорт read-only: система читает course, modules, pages, assignments, quizzes, outcomes и outcome alignments, но не публикует изменения обратно в Canvas.

Явные связи Canvas Outcome → Assignment сохраняются как teacher-authored ground truth. После аудита
`GET /audits/{audit_run_id}/canvas-alignment` сопоставляет их с ML-связями `assesses` и возвращает
precision, recall, F1, mapping coverage, а также списки совпавших, пропущенных, лишних и не извлечённых пар.
Если необязательный Canvas endpoint временно недоступен, ранее импортированная разметка не удаляется.

Новые аудиты сохраняют score всех candidate-пар до фильтрации. Calibration endpoint выполняет threshold sweep,
учитывает `top_k`, показывает F1-кривую и диагностический порог. Рекомендация не применяется автоматически:
на малой выборке UI явно предупреждает о риске переобучения, а production-порог следует подтверждать на независимых курсах.
Из карточки можно запустить отдельный A/B-аудит с диагностическим порогом. Его config содержит
`experiment_type=canvas_threshold_validation` и `calibration_source_audit_id`, поэтому baseline не перезаписывается.

### Course Q&A

Вкладка «Вопросы к курсу» использует тот же course-scoped hybrid RAG: преподаватель задаёт вопрос по всему курсу
или выбранному модулю, а LiteLLM формирует ответ только по найденным chunks. Citation IDs проверяются на сервере;
неизвестная citation приводит к extractive fallback, а отсутствие подтверждающих источников — к явному отказу отвечать.
История хранится в `course_question_answers` и доступна через `GET /courses/{course_id}/qa`.

Показатели использования входят в `/courses/{course_id}/quality-metrics`: количество вопросов, grounded rate
и средняя confidence. Q&A не использует данные и ответы учащихся и ничего не публикует обратно в Canvas.

### Canvas Change Set

Принятые преподавателем remediation drafts собираются в read-only пакет переноса. Для каждого элемента сервис
определяет операцию `create_page`, `create_assignment` или `update_assignment`, Canvas API path, модуль и исходный
Assignment ID. Обновление assignment считается готовым только при доказуемом mapping через Canvas document metadata;
иначе пакет требует ручного выбора цели. Markdown предназначен для преподавателя, JSON — для будущего подтверждаемого
write-back workflow. Сам endpoint не вызывает mutating Canvas API.

### Human feedback и ML dataset

Преподаватель отмечает Course Q&A как `helpful` или `unhelpful`; каждое изменение сохраняется отдельным event.
Экспорт `course-ml-feedback-*.jsonl` объединяет reviewed Q&A, findings, Copilot decisions и Canvas alignment labels.
По умолчанию reviewer/comment исключены из файла. Canvas-пары, отсутствующие в teacher-authored alignments, помечаются
`weak_negative=true`, поскольку исходная разметка может быть неполной. Это evaluation/training artifact, а не
автоматическое дообучение production-модели.

### Evaluation Protocol

Встроенный runner формирует сохраняемый протокол испытаний без shell-доступа и LLM-вызовов. Он фиксирует версию
методики, SHA-256 benchmark dataset, пороги приёмки, Recall@K, MRR, abstention, assessment guard, labeled citation
support, offline p95, citation integrity, audit success rate и общую продолжительность. При наличии Canvas Outcome
Alignments в измерения включается teacher-grounded alignment evaluation. Markdown-протокол содержит программу,
методику, pass/fail и ограничения синтетической выборки. Полная статическая методика описана в
`docs/TEST_PROGRAM.md`.

Synthetic gate проверяет регрессии движка, а отдельный обязательный smoke использует student-visible index выбранного
курса и полный tutor selection path. Поэтому пустой, скрытый или фактически неретривируемый курс не получает общий
readiness `PASS`. Synthetic и effective deployment-конфигурации сохраняются отдельно: если production threshold или
provider перестаёт возвращать материал, course readiness также становится `FAIL`.

Детерминированный baseline и строгий CI-gate можно воспроизвести отдельно:

```powershell
python scripts/evaluate_student_tutor.py --json-out docs/STUDENT_TUTOR_BENCHMARK.json --markdown-out docs/STUDENT_TUTOR_BENCHMARK.md --strict
```

### Хранение данных тьютора

По умолчанию вопросы, ответы, citations и feedback хранятся 90 дней. Администратор организации может выбрать только
30, 90, 180 или 365 дней; обновление версионируется и записывается без содержимого переписки. Ученик видит действующий
срок в тьюторе и всегда может безвозвратно удалить только собственную историю курса. Удаление также убирает связанные
feedback events, а в техническом receipt остаются только scope, причина, версия политики и счётчики.

Celery Beat запускает общий retention-сервис ежедневно в 02:15 UTC. Защищённый administrator endpoint позволяет
проверить тот же purge вручную перед подключением планировщика на хосте. Сервисы `beat` уже описаны в development и
production compose-файлах; Canvas, материалы курса, memberships и Evaluation Protocol при очистке не изменяются.

### Карта программы и компетенций

Раздел `/workspace/programs` даёт методисту, архитектору программы и
администратору проверяемую межкурсовую карту. Для каждой компетенции видно, в
каком курсе она вводится, развивается или проверяется. Связанная ячейка открывает
цель курса, текст задания или ручное основание; `expected_answer`, данные учеников
и переписки в ответ не попадают.

Кнопка «Проверить маршрут» строит read-only аудит текущей карты: показывает
компетенции без курса или проверки, недоступные основания и осторожный сигнал,
если один этап компетенции явно повторён в нескольких курсах или заявленная
проверка стоит раньше обучения. Повтор остаётся кандидатом для методической
сверки: он может быть осознанной спиралью и не считается доказанной
избыточностью. Каждый сигнал открывается вместе
с курсами, основанием, уверенностью и статусом проверки; это не рейтинг качества
программы или преподавателей. Анализ и выдача ограничены, а неполный результат
помечается явно.

Администратору доступен `/workspace/programs/overview`: алфавитный портфель
программ с агрегированными числами курсов, компетенций, связей и заявленных
проверок. Сводка не показывает людей, оценки или учебную активность и не ранжирует
программы. Строка открывает выбранную карту; если маршрут уже содержит
компетенции, его evidence-backed аудит загружается автоматически.

Чтение доступно ролям `methodologist`, `program_designer` и `administrator`.
Создание программ, сборка канонической ленты курсов, добавление компетенций и
связей доступны только `program_designer` и `administrator`. Все эти действия
можно выполнить в контекстном редакторе над живой картой без ручных API-вызовов.
Изменения используют `expected_version` и сохраняют content-safe change event.
Курс, компетенция и evidence ID повторно проверяются в сервисе на принадлежность
одной организации; перестановка не может молча удалить уже включённый курс.

Архитектор программы и администратор также могут провести явную линию
предпосылки между двумя компетенциями и объяснить её. Циклические и межпрограммные
связи отклоняются. Методист видит линию, авторское обоснование, проверку исходной
компетенции и начало следующей; сервис лишь сверяет их позиции в сохранённой
карте и не делает вывод о готовности студента. Если карта не обновилась после
успешной записи, дальнейшие изменения блокируются до загрузки актуальной версии.

Основные endpoints:

- `GET/POST /organizations/{organization_id}/programs`;
- `GET /programs/{program_id}/map`;
- `GET /programs/{program_id}/audit-preview`;
- `GET /organizations/{organization_id}/program-administration-overview`;
- `GET /programs/{program_id}/authoring-context`;
- `GET /programs/{program_id}/courses/{course_id}/evidence-options`;
- `PUT /programs/{program_id}/courses`;
- `POST /programs/{program_id}/competencies`;
- `PUT /programs/{program_id}/contributions`.

В development доступен идемпотентный
`POST /organizations/{organization_id}/programs/demo`. Он создаёт две безопасные
демонстрационные дисциплины и показывает три состояния карты: проверяется,
только обучение и нет курса. В production demo seed по умолчанию отключён.

### Canvas Course Remediation Copilot

После аудита преподаватель может запросить исправление конкретного finding. Copilot выполняет CPU-only hybrid retrieval
только по документам выбранного курса, передаёт top-k фрагментов в OpenAI-compatible chat API и возвращает
структурированный черновик с проверенными citations. Для цели без материала создаётся проект учебного раздела,
для цели без задания — проверяемое задание, для Bloom mismatch — переработанная формулировка assessment.

```http
POST /findings/{finding_id}/copilot
Content-Type: application/json

{"top_k": 5, "language": "ru"}
```

Canvas остаётся read-only: Copilot ничего не публикует и не использует данные учеников. Без LLM-ключа работает
детерминированный template fallback. Настройки находятся в `backend/.env.example`; retrieval не требует GPU или pgvector.

Каждая генерация сохраняется как отдельный draft. Преподаватель может принять или отклонить его; одновременно принятой
остаётся только одна remediation для finding. История включается в `GET /audits/{audit_run_id}/report`, а UI позволяет
скачать полный JSON-отчёт. `GET /courses/{course_id}/audits/compare` сравнивает два последних завершённых аудита:
изменение покрытия, новые, исправленные и сохранившиеся findings.

Для воспроизводимой демонстрации в development доступна кнопка «Попробовать демо» и `POST /courses/demo`.
Endpoint идемпотентно создаёт небольшой проблемный модуль, три документа и уже завершённый аудит с findings,
готовыми для Copilot. В production demo seed по умолчанию отключён.

## Проверки качества

```powershell
pytest -q
Set-Location frontend
npm run lint
npm run build
```

Bloom baseline оценивается скриптом:

```powershell
python scripts\evaluate_multilabel.py --data data\bloom_dataset.jsonl --out docs\BASELINE_QUALITY_REPORT.json
```

Для objective extraction, assessment extraction, relation classification и finding detection доступен `POST /evaluate/course-audit`.

Продуктовые метрики курса доступны через `GET /courses/{course_id}/quality-metrics`: success rate аудитов, review rate, acceptance rate, resolved findings и последняя сводка покрытия.

## Ограничения MVP

- Alignment использует интерпретируемый lexical/module baseline; cross-encoder и NLI ещё не подключены.
- Confidence является инженерной оценкой и требует калибровки на независимой преподавательской выборке.
- Поддерживается Canvas read-only import; автоматическая публикация изменений исключена.
- Не анализируются ответы и персональные данные учеников.
- Это аудитор курса, а не LMS, редактор курса или универсальный педагогический AI-ассистент.

Дополнительное описание реализации: `docs/COURSE_QUALITY_AUDITOR.md`.
