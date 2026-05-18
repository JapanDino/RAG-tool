# План доработок по результатам ревью ТЗ

> Источник: ревью AI Engineer + Backend Architect по ТЗ «Разработка модели анализа образовательного контента на основе таксономии Блума»  
> Дата: 2026-05-03

---

## Приоритет 1 — Критично (блокирует соответствие ТЗ)

### P1-1. Сквозной pipeline: ingest → embed → classify → node
**Проблема:** После Canvas ingestion `KnowledgeNode.vec` и `prob_vector` не заполняются автоматически. Семантический поиск и граф не работают без ручного запуска отдельных job'ов.  
**Файлы:** `backend/app/routers/canvas.py`, `backend/app/tasks/tasks.py`, `backend/app/routers/nodes.py`  
**Что сделать:**
- После создания `KnowledgeNode` в `ingest_course` / `ingest_course_stream` автоматически запускать цепочку Celery-задач: `embed_nodes → classify_nodes`
- Создать Celery-задачу `classify_nodes(dataset_id)` которая вычисляет `prob_vector` для каждого узла через `classify_bloom_multilabel` и сохраняет в `KnowledgeNode`
- В `POST /nodes` вычислять `vec` из `title + context_text` через `embed_texts` если поле не передано явно

---

### P1-2. UniqueConstraint в SQLAlchemy-моделях
**Проблема:** `ON CONFLICT (chunk_id)`, `ON CONFLICT (chunk_id, level)`, `ON CONFLICT (dataset_id, from_node_id, to_node_id, method)` используются в задачах, но отсутствуют в декларативных моделях. При старте без миграций — ошибка PostgreSQL.  
**Файл:** `backend/app/models/models.py`  
**Что сделать:**
```python
# Embedding
__table_args__ = (UniqueConstraint("chunk_id", name="uq_embeddings_chunk_id"),)

# BloomAnnotation
__table_args__ = (UniqueConstraint("chunk_id", "level", name="uq_bloom_chunk_level"),)

# KnowledgeEdge
__table_args__ = (
    UniqueConstraint("dataset_id", "from_node_id", "to_node_id", "method",
                     name="uq_kedge_ds_from_to_method"),
)
```

---

### P1-3. Синхронизация bloom_annotations → KnowledgeNode.prob_vector
**Проблема:** `annotate_dataset` обновляет `bloom_annotations` (на уровне чанков), но `KnowledgeNode.prob_vector` не пересчитывается. После переаннотирования граф показывает устаревшие данные.  
**Файлы:** `backend/app/tasks/tasks.py` (функция `annotate_dataset`)  
**Что сделать:**
- В конце `annotate_dataset` найти все `KnowledgeNode` для dataset_id, у которых `chunk_id` совпадает с аннотированными чанками
- Пересчитать `prob_vector` из свежих `BloomAnnotation` и обновить узлы

---

### P1-4. Реализовать NODE_EXTRACTOR=llm
**Проблема:** `node_extractor.py:192` выбрасывает `RuntimeError("not implemented")`. LLM-режим — качественно лучший вариант для образовательных концептов, предусмотренный ТЗ.  
**Файл:** `backend/app/services/node_extractor.py`  
**Что сделать:**
- Реализовать `LLMNodeExtractor.extract(text)` — промпт к LLM с инструкцией выделить концепты/термины/формулы из текста
- Промпт должен возвращать JSON-список `[{"title": "...", "context": "..."}]`
- Использовать существующий `chat_completion_json` из `openai_client.py`
- Добавить fallback к `NatashaNerExtractor` при ошибке LLM

---

## Приоритет 2 — Важно (снижает качество результата)

### P2-1. Улучшить эмбеддинг-модель для русского языка
**Проблема:** `multilingual-e5-small` (384-dim) — минимальная модель серии, заметно хуже для русского RAG. Zero-padding до 1536 архитектурно спорен.  
**Файл:** `backend/app/services/embedding_provider.py`  
**Что сделать:**
- Сменить дефолт на `intfloat/multilingual-e5-large` (1024-dim) или `deepvk/USER-bge-m3` (1024-dim)
- Обновить дефолтный `dim` с 1536 → 1024 (или оставить настраиваемым через `EMBEDDING_DIM`)
- Написать миграцию для пересчёта существующих эмбеддингов при смене модели

---

### P2-2. Усилить промпт для мульти-лейбл LLM-классификации
**Проблема:** `build_bloom_multilabel_prompt` (`prompt.py:42-69`) не содержит описаний уровней Блума и примеров — в отличие от `build_bloom_prompt` (строки 12-39).  
**Файл:** `backend/app/utils/prompt.py`  
**Что сделать:**
- Добавить `BLOOM_INSTRUCTIONS` (описание каждого из 6 уровней) в `build_bloom_multilabel_prompt`
- Добавить 2-3 few-shot примера с ожидаемым JSON-ответом
- Добавить поддержку `rubric: str | None` — передавать активный rubric в промпт (аналогично `build_bloom_prompt`)

---

### P2-3. HNSW-индекс на knowledge_nodes.vec
**Проблема:** `get_graph` выполняет O(N²) pgvector-запросов без индекса. При 500 узлах — 500 sequential scan.  
**Файлы:** `backend/app/models/models.py`, новая миграция  
**Что сделать:**
```sql
CREATE INDEX ON knowledge_nodes USING hnsw (vec vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```
- Добавить аннотацию в модель через `Index("ix_knode_vec_hnsw", "vec", postgresql_using="hnsw", postgresql_with={"m": 16})`

---

### P2-4. Исправить JobType.export в queue.py
**Проблема:** `queue.py:93-94` — `elif job.type == JobType.export: pass`. Задача export навсегда остаётся в статусе `queued`.  
**Файл:** `backend/app/tasks/queue.py`  
**Что сделать:**
- Реализовать логику запуска export-задачи (или удалить `JobType.export` если не используется)

---

### P2-5. Endpoint GET /datasets/{id}/ml-metrics
**Проблема:** Hamming Loss и F1 micro/macro есть только в CLI-скрипте, недоступны через API.  
**Файлы:** `backend/app/routers/evaluate.py` (или новый роутер), `scripts/evaluate_multilabel.py`  
**Что сделать:**
- Перенести `_hamming_loss`, `_f1_micro`, `_f1_macro` из скрипта в `backend/app/utils/quality.py`
- Добавить `GET /datasets/{id}/ml-metrics` → считать метрики по `node_labels` для датасета
- Вернуть `{"hamming_loss": float, "f1_micro": float, "f1_macro": float, "n_samples": int}`

---

### P2-6. Удалить bloom_classifier.py (мёртвый код)
**Проблема:** `backend/app/services/bloom_classifier.py` реализует дублирующий классификатор (5 слов на уровень), нигде не импортируется в основном пайплайне.  
**Что сделать:**
- Убедиться что файл нигде не импортируется: `grep -r "bloom_classifier" backend/`
- Удалить файл
- Обновить `__init__.py` если нужно

---

### P2-7. Исправить drift correction в bloom.py
**Проблема:** `bloom.py:117-119` — всё rounding error вешается на `P_create` (последний элемент), систематически сдвигая его.  
**Файл:** `backend/app/utils/bloom.py`  
**Что сделать:**
```python
# Вместо: probs[-1] = round(probs[-1] + drift, 3)
# Добавлять drift к элементу с наибольшим значением:
max_idx = probs.index(max(probs))
probs[max_idx] = round(probs[max_idx] + drift, 3)
```
- То же исправить в `bloom_multilabel.py:61-63` (дублирующий код — вынести в утилиту)

---

## Приоритет 3 — Желательно (улучшение качества)

### P3-1. Загрузка модулей Canvas как структурных единиц
**Проблема:** `canvas_client.py:131` содержит `list_modules()`, но при ingestion модули игнорируются.  
**Файлы:** `backend/app/routers/canvas.py`, `backend/app/services/canvas_client.py`  
**Что сделать:**
- При ingestion вызывать `list_modules()` и сохранять структуру модулей в `model_info` документа
- Опционально: создавать отдельный `Document` на каждый модуль для сохранения структуры курса

---

### P3-2. Валидация prob_vector == 6 элементов
**Проблема:** `KnowledgeNode.prob_vector` — нетипизированный `JSON`, нет гарантии 6 элементов.  
**Файл:** `backend/app/schemas/schemas.py` (или отдельная Pydantic-схема)  
**Что сделать:**
```python
from pydantic import field_validator

@field_validator("prob_vector")
@classmethod
def validate_prob_vector(cls, v):
    if v is not None and len(v) != 6:
        raise ValueError(f"prob_vector must have exactly 6 elements, got {len(v)}")
    return v
```

---

### P3-3. Тесты для ключевых ML-компонентов
**Проблема:** Только 4 теста; `bloom_multilabel`, `chunking`, `embedding`, `node_extractor` не покрыты.  
**Файлы:** `tests/` (новые файлы)  
**Что сделать:**
- `tests/test_bloom_multilabel.py` — тесты `classify_bloom_multilabel`: проверить что возвращает список из 6 float, сумма ≈ 1.0, известные глаголы попадают в правильный уровень
- `tests/test_chunking.py` — тесты `split_into_chunks`: граничные случаи (пустая строка, текст < min_len, текст > max_chars), overlap работает
- `tests/test_evaluate_multilabel.py` — тесты `_hamming_loss`, `_f1_micro`, `_f1_macro` с вручную посчитанными значениями

---

### P3-4. Ограничение размера файла при веб-загрузке
**Проблема:** `POST /datasets/{id}/documents` читает весь файл в память без ограничения размера.  
**Файл:** `backend/app/routers/datasets.py`  
**Что сделать:**
```python
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 20 * 1024 * 1024))  # 20 MB default

data = await file.read(MAX_UPLOAD_SIZE + 1)
if len(data) > MAX_UPLOAD_SIZE:
    raise HTTPException(413, "File too large")
```

---

### P3-5. Улучшить разбивку предложений в node_extractor
**Проблема:** `SENT_SPLIT_RE = re.compile(r"[.!?\n]+")` не обрабатывает русские сокращения (`т.е.`, `рис. 1`, `д-р`).  
**Файл:** `backend/app/services/node_extractor.py`  
**Что сделать:**
- Использовать `re.split(r'(?<![А-Яа-яA-Za-z]\.[А-Яа-яA-Za-z])[.!?]\s+', text)` с negative lookbehind для сокращений
- Или подключить `razdel` (библиотека для русской токенизации): `from razdel import sentenize`

---

### P3-6. Добавить GET /jobs (список задач)
**Проблема:** Нет способа получить историю задач без хранения job_id на клиенте.  
**Файл:** `backend/app/routers/jobs.py`  
**Что сделать:**
- `GET /jobs?dataset_id=X&status=running&type=index_dataset&limit=20&offset=0`
- Вернуть пагинированный список с полями `id, type, status, created_at, finished_at, error`

---

### P3-7. Исправить get_db: добавить rollback при исключении
**Проблема:** `session.py:9-14` — `get_db` не делает `rollback` при исключении в роутере.  
**Файл:** `backend/app/db/session.py`  
**Что сделать:**
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

---

## Сводная таблица

| ID | Приоритет | Затраты | Файлы | Статус |
|---|---|---|---|---|
| P1-1 | Критично | ~1 день | `canvas.py`, `tasks.py`, `nodes.py` | ✅ Выполнено |
| P1-2 | Критично | ~2 ч | `models.py` | ✅ Выполнено |
| P1-3 | Критично | ~3 ч | `tasks.py` | ✅ Выполнено |
| P1-4 | Критично | ~4 ч | `node_extractor.py` | ✅ Выполнено |
| P2-1 | Важно | ~3 ч + миграция | `embedding_provider.py` | ✅ Выполнено |
| P2-2 | Важно | ~1 ч | `prompt.py` | ✅ Выполнено |
| P2-3 | Важно | ~1 ч | `models.py` + миграция | ✅ Выполнено |
| P2-4 | Важно | ~30 мин | `queue.py` | ✅ Выполнено |
| P2-5 | Важно | ~2 ч | `quality.py`, `evaluate.py` | ✅ Выполнено |
| P2-6 | Важно | ~15 мин | `bloom_classifier.py` | ✅ Выполнено |
| P2-7 | Важно | ~30 мин | `bloom.py`, `bloom_multilabel.py` | ✅ Выполнено |
| P3-1 | Желательно | ~2 ч | `canvas.py`, `canvas_client.py` | ✅ Выполнено |
| P3-2 | Желательно | ~30 мин | `schemas.py` | ✅ Выполнено |
| P3-3 | Желательно | ~3 ч | `tests/` | ✅ Выполнено |
| P3-4 | Желательно | ~30 мин | `datasets.py` | ✅ Выполнено |
| P3-5 | Желательно | ~1 ч | `node_extractor.py` | ✅ Выполнено |
| P3-6 | Желательно | ~1 ч | `jobs.py` | ✅ Выполнено |
| P3-7 | Желательно | ~15 мин | `session.py` | ✅ Выполнено |
