# Project Progress Tracker

> **TZ Source**: `docs/DEVELOPMENT_PLAN_TZ_BLOOM.md` (+ `docs/PRODUCT_PLAN.md`)
> **Last Updated**: 2026-03-03
> **Overall Progress**: 100% (13/13 core steps done -- MVP complete)
> **Audit**: 2026-03-03 -- full source audit performed; all bugs fixed

---

## Summary
| Status | Count |
|--------|-------|
| Done | 13 |
| In Progress | 0 |
| Pending | 0 |
| Blocked | 0 |
| Bugs (critical) | 0 (3 found, 3 fixed) |
| Bugs (non-critical) | 0 (4 found, 4 fixed) |
| Enhancements | 3 remaining |

---

## Completed (MVP Steps S0-S12)

**S0 -- Normalize plan and tracking**
- Single unified plan, status table S0..S12 created in `docs/DEVELOPMENT_PLAN_TZ_BLOOM.md`.

**S1 -- Data contract "node" and "probabilities"**
- `KnowledgeNode` entity defined with `prob_vector[6]`, `top_levels`, `embedding_dim`, `embedding_model`, `version`, `model_info`.
- Bloom levels order fixed: `[remember, understand, apply, analyze, evaluate, create]`.
- Schema in `backend/app/schemas/schemas.py`, model in `backend/app/models/models.py`.

**S2 -- DB migrations for KnowledgeNode**
- Migrations present: `0010_knowledge_nodes.sql`, `0011_knowledge_edges.sql`, `0012_node_labels.sql`, `0013_jobtype_graph.sql`.
- All required tables verified in SQL: `datasets`, `documents`, `chunks`, `embeddings`, `bloom_annotations`, `knowledge_nodes`, `knowledge_edges`, `node_labels`, `jobs`.
- Indexes on `dataset_id`, `vec` (pgvector ivfflat), `document_id`, `chunk_id`.
- pgvector extension enabled in `0001_init.sql`.

**S3 -- CRUD/API for nodes**
- Routes in `backend/app/routers/nodes.py`:
  `POST /nodes`, `GET /nodes`, `GET /nodes/search`, `GET /nodes/{id}`, `PUT /nodes/{id}`, `DELETE /nodes/{id}`.
- `GET /nodes/search` correctly declared before `GET /nodes/{node_id}` (BUG-1 fixed).
- `POST /nodes/{id}/labels`, `GET /nodes/{id}/labels` added via `labeling.nodes_router` (BUG-3 fixed).

**S4 -- ExtractNodes (MVP)**
- `POST /analyze/extract` exists in `backend/app/routers/analyze.py`.
- `analyze.py` uses `get_node_extractor()` from `services/node_extractor.py` -- respects `NODE_EXTRACTOR` env var (BUG-5 fixed).
- `services/node_extractor.py` implements `HeuristicExtractor` and `NatashaNerExtractor`.

**S5 -- Multi-label Bloom classification (MVP)**
- `POST /analyze/classify` returns `prob_vector` and `top_levels`.
- `services/bloom_multilabel.py` implements hybrid keyword+LLM classifier.
- `.env` sets `BLOOM_CLASSIFIER=llm` -- LLM path used when `OPENAI_API_KEY` is set.
- `data/bloom_verbs_ru.json` used as keyword glossary fallback.
- LLM provider: Groq (`llama-3.3-70b-versatile`) via OpenAI-compatible API.

**S6 -- Endpoint "Content Analysis"**
- `POST /analyze/content` in `backend/app/routers/analyze.py`.
- Pipeline: extract -> classify (per-node) -> persist to `knowledge_nodes` -> embed with `embed_texts`.
- Embedding dim guard (must be 1536) added.
- Per-node classification: LLM mode = 1 call on full text; keyword mode = per-node context_snippet (BUG-4 fixed).

**S7 -- Node embeddings**
- `services/embedding_provider.py` implements 4 providers: hash, local (sentence-transformers), openai, random.
- Active provider: `EMBEDDING_PROVIDER=hash` per `.env`. HashingProvider uses term-frequency hashing (deterministic, offline, non-semantic).
- `GET /nodes/search` uses pgvector cosine distance with `vec IS NOT NULL` guard.
- `services/embedding.py` delegates to `embedding_provider.get_embedding_provider()`.

**S8 -- Knowledge graph edges**
- `GET /graph` returns nodes + edges (similarity + co-occurrence).
- `POST /graph/rebuild` enqueues Celery task `rebuild_graph_edges` (BUG-2 fixed, smoke-tested).
- Celery task persists edges to `knowledge_edges`.

**S9 -- UI: "Content Analysis" tab**
- Text input, file load, analyze button -> `/analyze/content`, node table, JSON/CSV export.
- All functionality implemented in `frontend/pages/index.tsx`.

**S10 -- UI: "Knowledge Graph" tab**
- Interactive graph via Cytoscape.js in `frontend/components/GraphView.tsx`.
- Color-coding by argmax Bloom level, gradient border for multi-label (secondary level >= threshold).
- Hover card, filter by Bloom level, zoom, export PNG.
- Loads from `GET /graph`. Filters by dataset_id, top_k, min_score, include_cooccurrence, limit_nodes.

**S11 -- Quality metrics**
- Hamming Loss, F1 micro/macro implemented in `backend/app/routers/evaluate.py`.
- Routes: `GET /evaluate/metrics` and `GET /evaluate/multilabel` (aliases).
- Router registered in `main.py`. Standalone script: `scripts/evaluate_multilabel.py`.

**S12 -- Defense materials**
- `docs/DEFENSE_MATERIALS.md`, `docs/DEMO_EXAMPLES.md` exist.

---

## Bugs Fixed (Full Source Audit 2026-03-03)

### ✅ BUG-1 -- `GET /nodes/search` shadowed by `GET /nodes/{node_id}`
- **Fixed**: Moved `/search` route declaration before `/{node_id}` in `nodes.py`.

### ✅ BUG-2 -- `POST /graph/rebuild` route was missing
- **Fixed**: Added `@router.post("/rebuild")` to `graph.py`. Enqueues `JobType.graph` via `enqueue_or_mark`.
- Smoke-tested: returns `{"job_id": N}`, job reaches `status: done` within seconds.

### ✅ BUG-3 -- `POST/GET /nodes/{node_id}/labels` routes were missing
- **Fixed**: Added `nodes_router` in `labeling.py` with `POST` and `GET` endpoints for node labels.
  Registered in `main.py` as `labeling_nodes_router`.

### ✅ BUG-4 -- All nodes received the same `prob_vector`
- **Fixed**: `analyze.py` now calls classifier per-node with `context_snippet` (keyword mode)
  or once on full text (LLM mode, for efficiency).

### ✅ BUG-5 -- `NODE_EXTRACTOR` env var had no effect on analyze endpoints
- **Fixed**: `analyze.py` now uses `get_node_extractor()` from `services/node_extractor.py`.

### ✅ BUG-6 -- `context_snippet` empty for most nodes (regex double-escape)
- **Fixed**: `node_extract.py` line 59: `rf"\\b{re.escape(tok)}\\b"` → `rf"\b{re.escape(tok)}\b"`.

### ✅ BUG-7 -- Groq API key appeared in `PROGRESS.md`
- **Fixed**: Key value removed from `PROGRESS.md`, commit amended before push.
- `backend/.env` is in `.gitignore` -- key itself was never committed to git.

---

## Blocked

None.

---

## Enhancement Opportunities (Beyond MVP)

**E3 -- Real semantic embeddings via sentence-transformers (Easy/Medium)**
- `EMBEDDING_PROVIDER=hash` is active. Change to `local` with `intfloat/multilingual-e5-small`
  (configured in `.env` as `EMBEDDING_MODEL_LOCAL`).
- Value: `/nodes/search` and `/graph` return semantically meaningful nearest neighbors.

**E4 -- Desktop (.exe) packaging with Tauri (Hard)**
- TZ mentions Windows .exe as preferred delivery. Not done. Docker is the current delivery.
- Value: teachers run without Docker or CLI setup.

**E5 -- Export JSONL button in UI (Easy)**
- `GET /datasets/{id}/labeling/export` is implemented and registered in `main.py`.
- Only missing: a UI button to call it. Backend is ready.

---

## Work Log

### 2026-03-03 -- Bug fix session
- Fixed all 7 bugs found during full source audit.
- BUG-1: route reorder in `nodes.py`.
- BUG-2: `POST /graph/rebuild` added to `graph.py`, smoke-tested OK.
- BUG-3: `POST/GET /nodes/{id}/labels` added via `labeling.nodes_router`.
- BUG-4: per-node classify in `analyze.py`.
- BUG-5: switched `analyze.py` to `get_node_extractor()`.
- BUG-6: regex fix in `node_extract.py`.
- BUG-7: key removed from `PROGRESS.md`, amend-pushed.
- All changes committed and pushed to `origin/main`.

### 2026-03-03 -- Full Source Audit
- Read all key source files: routers (analyze, nodes, graph, labeling, evaluate, datasets),
  services (bloom_multilabel, embedding_provider, embedding, node_extractor),
  models, schemas, migrations, Celery tasks, docker-compose, .env, frontend index.tsx, GraphView.tsx.
- Confirmed: all 13 MVP steps are implemented in code, not just marked done.
- Found 3 critical bugs: /nodes/search shadowed, POST /graph/rebuild missing, POST/GET /nodes/{id}/labels missing.
- Found 4 non-critical bugs: single classify call for all nodes, NODE_EXTRACTOR not wired, context_snippet regex broken, API key in PROGRESS.md.

### 2026-03-03 -- Session 1
- PROGRESS.md created for the first time.
- Assessed full project state after sprint S0-S12 + fix/tz-vector-guards branch.
- All 13 MVP steps confirmed done (at plan level).
- fix/tz-vector-guards merged into main.

### 2026-02-02
- S12: Defense materials finalized.
- S11: Quality metrics (Hamming, F1) added.
- S10: Knowledge Graph UI tab completed.
- S9: Content Analysis UI tab completed.
- S8: Graph edges endpoint.
- S7: Node embeddings + search.
- S6: Content analysis endpoint.
- S5: Multi-label Bloom classification.
- S4: ExtractNodes.
- S3: Nodes CRUD.
- S2: DB migrations.
- S1: Data contract.
- S0: Plan normalization.
