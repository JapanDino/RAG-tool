# Программа и методика испытаний Course Quality Auditor

## 1. Цель испытаний

Подтвердить, что сервис воспроизводимо находит релевантные материалы курса, отказывается отвечать без подтверждающего
контекста, защищает проверочные задания, сохраняет проверяемые цитаты и стабильно выполняет основной course-audit
pipeline.

## 2. Объект испытаний

- CPU-only hybrid retrieval: BM25-подобный lexical score и deterministic hash embeddings;
- Student Tutor, RAG Copilot и Instructor Course Q&A;
- Course Audit pipeline;
- Canvas Outcome Alignment evaluation, если в курсе есть teacher-authored связи.

LiteLLM не вызывается в обязательном offline protocol: это исключает влияние сети, стоимости и изменчивости модели
на regression-результат. Реальный LiteLLM проверяется отдельно интеграционным smoke-тестом.

## 3. Показатели назначения и критерии приёмки

| Показатель | Порог | Назначение |
|---|---:|---|
| Tutor Retrieval Recall@K | ≥ 0.90 | Релевантный документ присутствует в top-k |
| Tutor Retrieval MRR | ≥ 0.90 | Релевантный документ находится достаточно высоко |
| Abstention accuracy | = 1.00 | Система не возвращает источник для неподдержанного вопроса |
| Assessment guard accuracy | = 1.00 | Готовые ответы блокируются, нормальная помощь остаётся доступной |
| Labeled citation support | = 1.00 | Выбранные синтетические evidence содержат размеченные опорные термины |
| Offline case p95 | ≤ 250 ms | Retrieval и guard подходят для интерактивного пути без учёта модели и сети |
| Student-visible course index | = 1 | В реальном курсе есть доступный chunk, извлекаемый полным tutor path |
| Citation integrity | = 1.00 | Document/chunk принадлежат курсу, quote содержится в chunk |
| Audit success rate | ≥ 0.90 | Завершённые запуски course audit не падают |
| Evaluation runtime | ≤ 5000 ms | Offline protocol подходит для интерактивной демонстрации |

Citation integrity и audit success rate становятся обязательными после появления соответствующих наблюдений.
До этого они отображаются как `NOT RUN`, а не как искусственный ноль.

## 4. Порядок проведения

1. Выбрать курс в Course Quality Auditor.
2. Нажать «Запустить испытания».
3. Зафиксировать версию protocol, dataset name и SHA-256.
4. Выполнить student-tutor benchmark на `data/student_tutor_eval.jsonl`.
5. Проверить retrieval, abstention, assessment guard, labeled citation support и offline p95.
6. Выполнить course-scoped smoke по student-visible index через полный tutor selection path.
7. Проверить все сохранённые Q&A/Copilot citations относительно документов и chunks выбранного курса.
8. Рассчитать success rate terminal audit runs.
9. При наличии Canvas Outcome Alignments добавить precision/recall/F1 относительно teacher ground truth.
10. Сохранить immutable protocol snapshot и скачать Markdown/JSON.

## 5. Воспроизводимость

- benchmark dataset фиксируется SHA-256;
- protocol хранит thresholds, metrics, case-level retrieval results и продолжительность;
- embeddings для обязательного benchmark всегда deterministic `hash:v1:1536`;
- protocol отдельно фиксирует deterministic benchmark config и effective
  provider/min score/candidate cap для course-scoped runtime smoke;
- повторный запуск создаёт новый protocol, не изменяя предыдущий результат.

## 6. Ограничения

Bundled tutor dataset является синтетическим regression-набором и не доказывает production-качество сам по себе.
Labeled citation support — лексический proxy, а offline p95 не включает базу данных, сеть или hosted model. Для
окончательной приёмки следует собрать независимую teacher-validated выборку реальных курсов. Отсутствующие Canvas
alignments трактуются только как weak negatives, поскольку преподавательская разметка может быть неполной.
Course-scoped smoke намеренно зависит от effective deployment configuration: изменение provider или retrieval limits
может изменить readiness, поэтому эта конфигурация сохраняется вместе с результатом.
