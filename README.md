# RAG-tool — Анализ образовательного контента по таксономии Блума

Инструмент для автоматической разметки учебных материалов по **пересмотренной таксономии Блума** (Anderson & Krathwohl, 2001). Импортирует курсы из **Canvas LMS**, разбивает тексты на смысловые узлы, классифицирует их по 6 когнитивным уровням и строит **граф знаний** с семантическими связями.

---

## Содержание

- [Что делает инструмент](#что-делает-инструмент)
- [Уровни таксономии Блума](#уровни-таксономии-блума)
- [Архитектура](#архитектура)
- [Стек технологий](#стек-технологий)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [API](#api)
- [Тестирование](#тестирование)
- [Структура проекта](#структура-проекта)

---

## Что делает инструмент

```
Canvas LMS ──► Импорт контента ──► Разбивка на чанки
                                         │
                    ┌────────────────────▼────────────────────┐
                    │         Классификатор Блума              │
                    │  keyword (offline) │ LLM (OpenAI GPT)   │
                    └────────────────────┬────────────────────┘
                                         │  prob_vector[6]
                    ┌────────────────────▼────────────────────┐
                    │          Узлы знаний (Knowledge Graph)   │
                    │  title · context · top_levels · vec      │
                    └────────────────────┬────────────────────┘
                                         │
                         pgvector HNSW (косинусное сходство)
                                         │
                    ┌────────────────────▼────────────────────┐
                    │    Граф с рёбрами: similarity + co-occ   │
                    │    Интерактивная визуализация в UI        │
                    └─────────────────────────────────────────┘
```

**Основные возможности:**

- 📥 **Импорт из Canvas LMS** — страницы, задания, тесты, обсуждения, файлы (PDF, DOCX, TXT)
- 🧠 **Двухрежимная классификация** — быстрый keyword-классификатор (офлайн) и LLM-режим (GPT-4o-mini)
- 📊 **Вектор вероятностей** `[p_remember, p_understand, p_apply, p_analyze, p_evaluate, p_create]` для каждого узла
- 🕸️ **Граф знаний** — семантические рёбра (pgvector HNSW) + рёбра совместной встречаемости
- 🔍 **Семантический поиск** по узлам курса
- 🏷️ **Ручная разметка** — очередь узлов для верификации человеком
- 📈 **Метрики качества** — Hamming loss, F1-micro, F1-macro по multi-label аннотациям

---

## Уровни таксономии Блума

| Уровень | Ключевые глаголы | Пример задачи |
|---|---|---|
| **Remember** — Запомни | назовите, перечислите, определите | «Перечислите 5 алгоритмов классификации» |
| **Understand** — Пойми | объясните, опишите, классифицируйте | «Объясните компромисс смещение-дисперсия» |
| **Apply** — Примени | используйте, вычислите, решите | «Обучите KNN на датасете iris, вычислите F1» |
| **Analyze** — Анализируй | сравните, выделите, разберите | «Сопоставьте XGBoost и случайный лес» |
| **Evaluate** — Оценивай | оцените, аргументируйте, обоснуйте | «Докажите или опровергните утверждение» |
| **Create** — Создавай | разработайте, спроектируйте, создайте | «Спроектируйте пайплайн детекции мошенничества» |

Классификатор возвращает **нормированный вектор вероятностей** (сумма = 1.0) по всем 6 уровням одновременно — это позволяет работать с пограничными случаями (e.g. `analyze 0.58 + understand 0.19`).

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐ │
│  │ frontend │   │ backend  │   │  worker  │   │  db (pgvec)  │ │
│  │ Next.js  │──►│ FastAPI  │──►│  Celery  │   │  PostgreSQL  │ │
│  │ :3000    │   │ :8000    │   │          │   │  + pgvector  │ │
│  └──────────┘   └────┬─────┘   └────┬─────┘   └──────────────┘ │
│                       │              │          ┌──────────────┐ │
│                       └──────────────┴─────────►│    Redis     │ │
│                                                 │   (broker)   │ │
│                                                 └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Слои бэкенда

| Слой | Описание |
|---|---|
| **Routers** (`/canvas`, `/nodes`, `/graph`, `/datasets`) | HTTP API — FastAPI |
| **Tasks** (`index_dataset`, `annotate_dataset`, `rebuild_graph_edges`) | Async Celery tasks |
| **Services** | `chunking`, `embedding_provider`, `node_extractor`, `bloom_multilabel` |
| **Utils** | `bloom.py` — keyword classifier; `vector.py` — pgvector литерал |
| **Models** | SQLAlchemy ORM: Dataset, Document, Chunk, KnowledgeNode, KnowledgeEdge |

---

## Стек технологий

### Backend
| Технология | Версия | Роль |
|---|---|---|
| **FastAPI** | ≥0.110 | REST API |
| **SQLAlchemy** | 2.0 | ORM |
| **PostgreSQL + pgvector** | pg16 + pgvector | Хранение векторов, HNSW-индекс |
| **Celery + Redis** | 5.3 / 7 | Очередь задач |
| **sentence-transformers** | ≥3.0 | Локальные эмбеддинги (`multilingual-e5-large`, 1024-dim → pad до 1536) |
| **natasha** | ≥1.6 | Русскоязычный NER для извлечения узлов |
| **razdel** | любая | Русскоязычная сегментация предложений |
| **OpenAI API** | — | LLM-классификация (опционально) |
| **pypdf / pytesseract** | — | Извлечение текста из PDF (с OCR) |

### Frontend
| Технология | Роль |
|---|---|
| **Next.js** | React SSR фреймворк |
| **TypeScript** | Типизация |
| **vis-network** | Визуализация графа знаний |

### Инфраструктура
| Технология | Роль |
|---|---|
| **Docker Compose** | Оркестрация всех сервисов |
| **pgvector HNSW** | Косинусный поиск ближайших соседей (m=16, ef_construction=64) |
| **SQL-миграции** | Версионированные `.sql`-файлы, применяются при старте |

---

## Быстрый старт

### Требования
- Docker + Docker Compose
- 8 GB RAM (для `multilingual-e5-large`; можно переключиться на `hash`-провайдер)

### 1. Клонировать и настроить

```bash
git clone https://github.com/JapanDino/RAG-tool.git
cd RAG-tool
cp backend/.env.example backend/.env
```

Отредактируйте `backend/.env`:

```env
# Обязательно для Canvas-импорта
CANVAS_URL=https://your-canvas-instance.edu
CANVAS_TOKEN=your_canvas_api_token

# Эмбеддинги: local (семантические) | hash (быстро, без GPU) | openai
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL_LOCAL=intfloat/multilingual-e5-large

# LLM-классификация (опционально, по умолчанию — keyword)
# BLOOM_CLASSIFIER=llm
# OPENAI_API_KEY=sk-...
# LLM_MODEL=gpt-4o-mini
```

### 2. Запустить

```bash
docker compose up -d
```

Сервисы поднимутся автоматически. Миграции БД применяются при старте backend-контейнера.

| Сервис | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

### 3. Импортировать курс из Canvas

В UI перейдите на вкладку **Canvas**, введите ID курса и нажмите **Импортировать**. Прогресс отображается в реальном времени через SSE-стрим.

Или через API:

```bash
curl -X POST http://localhost:8000/canvas/ingest-stream \
  -H "Content-Type: application/json" \
  -d '{"course_id": 12345, "dataset_id": 1, "max_nodes_per_doc": 30}'
```

---

## Конфигурация

### Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://rag:rag_pass@db:5432/rag_db` | Строка подключения к БД |
| `REDIS_URL` | `redis://redis:6379/0` | Брокер Celery |
| `EMBEDDING_PROVIDER` | `local` | `local` / `openai` / `hash` |
| `EMBEDDING_MODEL_LOCAL` | `intfloat/multilingual-e5-large` | Модель sentence-transformers |
| `BLOOM_CLASSIFIER` | `keyword` | `keyword` (офлайн) / `llm` (OpenAI) |
| `ENABLE_CELERY` | `1` | `0` — синхронный режим без Redis |
| `CANVAS_URL` | — | URL инстанса Canvas LMS |
| `CANVAS_TOKEN` | — | API-токен Canvas |
| `CANVAS_TEXT_MAX_CHARS` | `120000` | Лимит символов при извлечении текста |
| `CANVAS_PDF_MAX_PAGES` | `25` | Макс. страниц PDF |
| `NODE_EXTRACTOR` | `local_ner` | `local_ner` / `heuristic` / `llm` |

### Режимы классификации

**keyword** (по умолчанию) — офлайн, детерминированный:
- Поиск Bloom-глаголов из `data/bloom_verbs_ru.json` + структурные паттерны
- Сглаживание Лапласа: `p(level) = (hits + 1) / (total + 6)`
- Точность ~75–83% на текстах с явными глаголами; деградирует на текстах без глаголов

**llm** — через OpenAI API:
- `BLOOM_CLASSIFIER=llm`, требует `OPENAI_API_KEY`
- Модель: `OPENAI_LLM_MODEL=gpt-4o-mini`
- Возвращает prob_vector + rationale; при ошибке API — fallback на keyword

---

## API

Полная документация: `http://localhost:8000/docs`

### Ключевые эндпоинты

```
GET  /canvas/courses                    — список доступных курсов Canvas
POST /canvas/ingest                     — импорт курса (sync)
POST /canvas/ingest-stream              — импорт курса (SSE stream)

GET  /datasets                          — список датасетов
POST /datasets                          — создать датасет
POST /datasets/{id}/index               — создать эмбеддинги чанков
POST /datasets/{id}/annotate?level=...  — аннотировать чанки по уровню Блума

GET  /nodes?dataset_id=...              — список узлов знаний
GET  /nodes/search?q=...                — семантический поиск по узлам
POST /nodes                             — создать узлы вручную

GET  /graph?dataset_id=...              — граф узлов + рёбра
POST /graph/rebuild                     — пересчитать рёбра (pgvector + co-occ)

POST /evaluate/{dataset_id}             — метрики качества разметки
```

---

## Тестирование

```bash
# Запустить все тесты
python -m pytest tests/ -v

# Только тесты классификатора
python -m pytest tests/test_bloom_multilabel.py -v

# Только тесты чанкинга
python -m pytest tests/test_chunking.py -v
```

Покрытие тестами (46 тестов):
- `test_bloom_multilabel.py` — keyword-классификатор, Bloom-уровни, drift-коррекция
- `test_chunking.py` — разбивка текста, overlap, русские аббревиатуры
- `test_evaluate_multilabel.py` — Hamming loss, F1-micro, F1-macro
- `test_validation.py` — валидация аннотаций
- `test_regressions.py` — регрессионные тесты API

---

## Структура проекта

```
RAG-tool/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, роутеры
│   │   ├── models/models.py         # SQLAlchemy ORM
│   │   ├── schemas/schemas.py       # Pydantic schemas + валидация prob_vector
│   │   ├── routers/
│   │   │   ├── canvas.py            # Canvas LMS импорт (sync + SSE)
│   │   │   ├── nodes.py             # CRUD узлов знаний
│   │   │   ├── graph.py             # Граф + rebuild
│   │   │   ├── datasets.py          # Датасеты, документы, индексация
│   │   │   └── evaluate.py          # Метрики качества
│   │   ├── services/
│   │   │   ├── chunking.py          # Разбивка текста (razdel-aware)
│   │   │   ├── embedding_provider.py # Local / OpenAI / Hash провайдеры
│   │   │   ├── node_extractor.py    # NER + heuristic + LLM экстракторы
│   │   │   └── bloom_multilabel.py  # Гибридный классификатор (keyword + LLM)
│   │   ├── tasks/
│   │   │   ├── tasks.py             # Celery tasks: index, annotate, graph
│   │   │   └── queue.py             # enqueue_or_mark (Celery / sync fallback)
│   │   └── utils/
│   │       ├── bloom.py             # Keyword classifier + Laplace smoothing
│   │       └── prompt.py            # Bloom prompt templates (RU)
│   ├── migrations/                  # SQL-миграции (0001–0017)
│   └── requirements.txt
├── frontend/
│   ├── pages/index.tsx              # Главная страница: граф, узлы, Canvas
│   ├── components/
│   │   ├── GraphView.tsx            # vis-network граф
│   │   └── JobStatus.tsx            # Статус async задач
│   └── lib/bloom-constants.ts       # Цвета и метки уровней Блума
├── data/
│   └── bloom_verbs_ru.json          # Словарь Bloom-глаголов (RU, ~200 слов)
├── tests/                           # pytest (46 тестов)
├── scripts/
│   ├── apply_migrations.sh          # Автоматическое применение миграций
│   └── db/init/                     # Инициализация pgvector + HNSW индексов
├── docs/
│   └── REMEDIATION_PLAN.md         # История исправлений и технический долг
└── docker-compose.yml
```

---

## Технические решения

### Эмбеддинги
- Модель по умолчанию: **`intfloat/multilingual-e5-large`** (1024 dim, мультиязычная)
- Векторы zero-padding до 1536 dim — совместимость с OpenAI `text-embedding-3-small`
- HNSW-индекс с `vector_cosine_ops` (m=16, ef_construction=64) для быстрого поиска

### Классификатор Блума
- **Keyword-режим**: Laplace smoothing по verb-hits + структурные regex-паттерны
- **LLM-режим**: GPT-4o-mini возвращает `prob_vector[6]` + rationale; fallback на keyword при любой ошибке
- Валидация prob_vector в Pydantic: ровно 6 элементов, каждый ∈ [0, 1], сумма ≈ 1.0 (±0.02)

### Canvas-интеграция
- Поддерживаемые типы: `syllabus`, `pages`, `assignments`, `quizzes`, `discussions`, `files`
- SSE-стрим для real-time прогресса без таймаутов прокси
- Идемпотентная повторная загрузка через `UPSERT` по `(dataset_id, document_id, title)`
- Module-map: узлы обогащаются метаданными модуля Canvas (`module_name`, `module_position`)

---

## Лицензия

MIT
