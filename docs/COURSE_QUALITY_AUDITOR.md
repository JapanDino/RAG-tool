# Course Quality Auditor: реализация vertical slice

## Продуктовое решение

Первый vertical slice проверяет согласованность `Learning Objective → Material → Assessment`. Автоматические выводы считаются рекомендациями до решения преподавателя.

Опасные ошибки системы:

1. Ложный finding, заставляющий преподавателя исправлять корректный курс.
2. Пропущенная важная цель или отдельное задание.
3. Потеря evidence или пользовательского решения после повторного анализа.
4. Неверная интерпретация Bloom mismatch как абсолютной педагогической ошибки.

Для снижения риска каждый finding содержит evidence и confidence, поддерживает review workflow, а review переносится в следующий `AuditRun` по устойчивому fingerprint.

## Pipeline

```text
Course import
→ document classification
→ sentence-aware chunks with source offsets
→ objective and assessment extraction
→ Bloom classification
→ lexical/module candidate retrieval
→ relation validation baseline
→ three finding detectors
→ human review
```

Finding detectors:

- `objective_without_material`;
- `objective_without_assessment`;
- `bloom_mismatch`.

## Remediation Copilot

Для каждого поддерживаемого finding доступен RAG-черновик исправления. Retriever ограничивает кандидатов dataset выбранного
курса, сочетает BM25-подобный lexical score, CPU embedding similarity и module bonus. Source IDs, возвращённые LLM,
проверяются по фактически извлечённым chunks; неизвестные или отсутствующие citations приводят к безопасному template fallback.
Canvas-контент рассматривается как недоверенные данные и не может задавать инструкции генератору.

## Instructor Course Q&A

`POST /courses/{course_id}/qa` отвечает на вопросы преподавателя по всему курсу или выбранному модулю.
Retrieval остаётся локальным и course-scoped, LiteLLM получает только top-k фрагменты, а возвращённые citation IDs
проверяются по фактически найденным chunks. При ошибке модели используется extractive fallback; без достаточного
контекста сервис отказывается отвечать. `GET /courses/{course_id}/qa` возвращает последние 50 вопросов.

## Canvas Change Set

Accepted Copilot suggestions доступны как preview через `GET /courses/{course_id}/canvas-change-set` и скачиваются
в Markdown/JSON. Пакет содержит предполагаемый Canvas API method/path, модуль, target assignment, draft, rationale и
цитаты. Это handoff-артефакт, а не автоматическая публикация: ни один Canvas write endpoint не вызывается.

## Human feedback loop

Ответы Course Q&A получают teacher label `helpful`/`unhelpful` и append-only историю переходов. Course-level JSONL
экспорт собирает четыре типа примеров: Q&A, reviewed findings, accepted/rejected Copilot drafts и Canvas alignment
candidates. Reviewer metadata исключена по умолчанию. Отрицательные Canvas labels считаются weak negatives, чтобы
не выдавать отсутствие связи в потенциально неполной разметке за надёжный ground truth.

## Evaluation Protocol

`POST /courses/{course_id}/evaluation-protocols` запускает безопасный offline protocol и сохраняет immutable snapshot
результатов. Dataset идентифицируется SHA-256; каждый показатель имеет явный acceptance threshold и PASS/FAIL.
Протокол скачивается в Markdown/JSON и содержит методику, измерения, runtime и ограничения применимости.

Suggestions сохраняются в `course_copilot_suggestions` со статусами `draft`, `accepted`, `rejected`, моделью генерации,
retrieval method и полным набором citations. Принятие нового draft автоматически снимает прежний accepted draft для того
же finding. Audit report включает всю историю, а comparison endpoint показывает динамику между двумя завершёнными аудитами.

Development demo seed (`POST /courses/demo`) создаёт идемпотентный учебный пример и немедленно выполняет аудит.
Он нужен для защиты и smoke-тестов, не требует Canvas token и блокируется по умолчанию при `APP_ENV=production`.

## Versioning и идемпотентность

- Повторный импорт файла определяется по SHA-256.
- Canvas-документы обновляются по external ID и content hash.
- Canvas Outcomes сохраняются отдельными документами, а Outcome → Assignment links — как эталонная разметка преподавателя.
- `GET /audits/{audit_run_id}/canvas-alignment` измеряет precision/recall/F1 ML-связей относительно Canvas и показывает расхождения.
- Все objective-assessment candidate scores сохраняются до threshold/top-k фильтрации для воспроизводимой калибровки.
- `GET /audits/{audit_run_id}/canvas-alignment/calibration` строит F1-кривую и диагностический порог, но не меняет production config автоматически.
- Неуспешный ответ необязательного outcome-alignments endpoint не стирает последнюю успешную разметку.
- Повторный запуск того же `AuditRun` удаляет только его генерируемые артефакты и создаёт их заново.
- Новый запуск не удаляет старые результаты.
- Решения преподавателя копируются в совпадающий finding нового запуска и имеют отдельный `FindingReviewEvent` audit trail.

## Security baseline

- Проверяются расширение, MIME, размер файла и лимит документов.
- Файл сохраняется под UUID, исходное имя не используется как путь.
- Временный файл удаляется и после успешного разбора, и после ошибки.
- Canvas требует HTTPS, блокирует loopback/private адреса и поддерживает host allow-list.
- Canvas token и исходный текст документов не выводятся в логи.
- Production не запускается с wildcard CORS.
- Mutating API можно защитить переменной `API_WRITE_KEY`.

## Проверяемые критерии MVP

1. Создание курса и модулей.
2. Идемпотентная загрузка документов.
3. Извлечение целей и заданий с offsets.
4. Сохранение Bloom vector и model metadata.
5. Построение `teaches` и `assesses` с evidence.
6. Генерация трёх обязательных finding.
7. Confirm/reject/resolved workflow и журнал решений.
8. Alignment Matrix и course-level summary.
9. Асинхронный запуск через Celery с локальным sync fallback.
10. Versioned rerun без неконтролируемых дублей.
11. Canvas read-only import.
12. Оценка ML alignment по teacher-authored Canvas Outcome Alignments.
13. Unit, API и integration regression tests.

## Следующий рекомендуемый slice

После пилота на реальных курсах:

1. собрать независимую teacher-validated выборку;
2. измерить extraction/relations/findings отдельно;
3. сравнить lexical baseline с multilingual cross-encoder;
4. откалибровать confidence bands;
5. только затем добавить дополнительные finding: prerequisites, duplication и cognitive imbalance.
