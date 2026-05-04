# RAG-tool — Bloom's Taxonomy Knowledge Graph

> An educational content analysis pipeline that extracts concepts from text, classifies them across Bloom's six cognitive levels, and renders an interactive knowledge graph.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green?logo=fastapi)
![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-blue?logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ed?logo=docker)
![Tests](https://img.shields.io/badge/tests-46%20passing-brightgreen)

---

## What it does

1. **Upload or paste** educational text (lectures, syllabi, textbook chapters).
2. **Extract knowledge nodes** — key concepts and terms using NER (natasha) or regex heuristics.
3. **Classify each node** across Bloom's Taxonomy (Remember → Understand → Apply → Analyze → Evaluate → Create) using a fast keyword + morphology classifier (offline, no GPU required).
4. **Visualise** the result as an interactive graph where node colour = Bloom level, node size = concept frequency, and split-pie nodes show multi-level concepts.
5. **Evaluate** classifier quality with multilabel F1 / Hamming loss metrics via a built-in annotation queue.

---

## Stack

| Layer | Technology |
|---|---|
| **API** | FastAPI · Uvicorn · Pydantic v2 |
| **NLP** | pymorphy3 · natasha NER · sentence-transformers (`intfloat/multilingual-e5-large`) |
| **Database** | PostgreSQL 16 + pgvector extension |
| **Queue / Cache** | Redis · Celery |
| **Frontend** | Next.js 14 · React · Cytoscape.js |
| **OCR** | Tesseract · pdf2image · pdfminer |
| **Containerisation** | Docker Compose |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Next.js)                  │
│  Upload → Analyze → Graph View → Label Queue → Metrics  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / REST
┌────────────────────────▼────────────────────────────────┐
│                    FastAPI Backend                        │
│                                                          │
│  /analyze/content   ←──── NodeExtractor (natasha/regex) │
│  /analyze/classify  ←──── BloomClassifier (keyword/llm) │
│  /search            ←──── EmbeddingProvider (local/oai) │
│  /datasets          ←──── DatasetManager                │
│  /evaluate          ←──── MultilabelMetrics              │
└───────┬──────────────────────────────┬──────────────────┘
        │                              │
   PostgreSQL + pgvector            Redis + Celery
   (knowledge_nodes, docs)         (async jobs)
```

### Bloom classifier pipeline

```
raw text
   │
   ▼
_normalize_text()          ← pymorphy3 lemmatisation (Russian/mixed)
   │
   ├─ keyword matching     ← bloom_verbs_ru.json  (6 × ~30 lemmatised verbs)
   │
   └─ heuristic regex      ← HEURISTIC_PATTERNS   (structural cues: "семинар", "лабораторная"…)
          │
          ▼
   Laplace-smoothed probability vector [6]
          │
          ▼
   top_levels (≥ 0.20 threshold, max 2)
```

---

## Quick start

### Prerequisites
- Docker Desktop ≥ 24 (with Compose v2)
- 4 GB RAM free (the e5-large embedding model loads on first run)

### 1. Clone and configure

```bash
git clone https://github.com/JapanDino/RAG-tool.git
cd RAG-tool
cp backend/.env.example backend/.env
```

Edit `backend/.env` — only two keys are mandatory:

| Key | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://rag:rag_pass@db:5432/rag_db` | Change password in production |
| `EMBEDDING_PROVIDER` | `local` | `local` needs no API key; `openai` needs `OPENAI_API_KEY` |

### 2. Start

```bash
docker compose up --build
```

- Frontend: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>

### 3. First use

1. Open <http://localhost:3000>
2. Create a dataset (e.g. "Алгоритмы")
3. Paste or upload a lecture PDF
4. Click **Analyze** — the knowledge graph appears in ~5 seconds

---

## Environment variables

Full reference in [`backend/.env.example`](backend/.env.example).

| Variable | Values | Description |
|---|---|---|
| `EMBEDDING_PROVIDER` | `local` · `hash` · `openai` | Embedding backend |
| `EMBEDDING_MODEL_LOCAL` | `intfloat/multilingual-e5-large` | HuggingFace model ID |
| `BLOOM_CLASSIFIER` | `keyword` · `llm` | Classifier mode |
| `BLOOM_VERBS_PATH` | path | Override verb dictionary |
| `NODE_EXTRACTOR` | `local_ner` · `heuristic` | Concept extractor |
| `OPENAI_API_KEY` | `sk-…` | Required only for `openai` / `llm` modes |
| `OCR_PAGE_TIMEOUT_S` | `30` | Tesseract timeout per page (0 = off) |

---

## Project structure

```
RAG-tool/
├── backend/
│   ├── app/
│   │   ├── routers/          # FastAPI route handlers
│   │   │   ├── analyze.py    # /analyze — chunking, extraction, Bloom classification
│   │   │   ├── datasets.py   # /datasets — CRUD, labelling queue
│   │   │   ├── evaluate.py   # /evaluate — multilabel metrics
│   │   │   └── search.py     # /search — vector similarity search
│   │   ├── services/
│   │   │   ├── bloom_multilabel.py   # thin wrapper (env-driven classifier dispatch)
│   │   │   ├── chunking.py           # sentence-aware text splitter
│   │   │   ├── embedding.py          # embedding pipeline
│   │   │   ├── embedding_provider.py # local / hash / openai
│   │   │   └── node_extractor.py     # natasha NER + heuristic fallback
│   │   └── utils/
│   │       └── bloom.py      # keyword classifier, heuristic patterns, annotate_bloom()
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── components/
│   │   ├── GraphView.tsx     # Cytoscape.js knowledge graph
│   │   └── …
│   ├── pages/
│   │   └── index.tsx         # main SPA
│   └── lib/
│       └── bloom-constants.ts # level colours, shapes, labels
├── data/
│   ├── bloom_verbs_ru.json   # Russian Bloom verb dictionary (6 levels, ~200 entries)
│   └── bloom_dataset.jsonl   # labelled evaluation dataset
├── tests/
│   ├── test_bloom_classifier.py
│   ├── test_bloom_tz.py
│   ├── test_chunking.py
│   ├── test_evaluate_multilabel.py
│   └── test_smoke.py
├── scripts/
│   └── seed_dataset.py
└── docker-compose.yml
```

---

## Running tests

```bash
cd backend
pip install -r requirements.txt
pytest ../tests/ -v
# 46 passed in ~5 s (no network, no GPU required)
```

---

## Bloom's Taxonomy levels

| Level | Russian label | Colour | Typical verbs |
|---|---|---|---|
| Remember | Факты | blue | назовите, перечислите, определите |
| Understand | Понимание | green | объясните, сравните, почему |
| Apply | Применение | amber | решите, вычислите, используйте |
| Analyze | Анализ | orange | проанализируйте, выделите, структурируйте |
| Evaluate | Оценивание | violet | оцените, аргументируйте, докажите |
| Create | Создание | rose | создайте, разработайте, спроектируйте |

Graph nodes with two dominant levels show a split-pie (proportional to probability share between the top two levels).

---

## Classifier accuracy

Manual evaluation on 12 educational text fragments (mixed Russian):

| Metric | Value |
|---|---|
| Exact match (top level) | 75 % (9/12) |
| Partial match (level in top-2) | 83 % (10/12) |

Known limitation: heuristic pattern `\bвычисл` can fire on the adjective _вычислительный_ (computational), occasionally boosting **Apply** in text that belongs to **Analyze**. This is documented in `HEURISTIC_PATTERNS` and can be narrowed by replacing the regex with a verb-only lemma match.

---

## Contributing

1. Fork and create a feature branch.
2. Add / extend tests in `tests/`.
3. Run `pytest` — all 46 must pass.
4. Open a PR against `main`.

---

## License

MIT
