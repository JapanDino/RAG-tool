# Project Progress Tracker

> **TZ Source**: `docs/DEVELOPMENT_PLAN_TZ_BLOOM.md` (+ `docs/PRODUCT_PLAN.md`)
> **Last Updated**: 2026-03-03
> **Overall Progress**: 100% (13/13 core steps done -- MVP complete)
> **Audit**: 2026-03-03 -- full source audit performed; critical bugs found

---

## Summary
| Status | Count |
|--------|-------|
| Done | 13 |
| In Progress | 0 |
| Pending | 0 |
| Blocked | 0 |
| Bugs (critical) | 3 |
| Bugs (non-critical) | 4 |
| Enhancements | 5 |

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
  `POST /nodes`, `GET /nodes`, `GET /nodes/{id}`, `PUT /nodes/{id}`, `DELETE /nodes/{id}`.
- BUG: `GET /nodes/search` is declared AFTER `GET /nodes/{node_id}` -- FastAPI will match
  `/nodes/search` as `node_id="search"` (404). Route order causes shadowing. See Bugs section.

**S4 -- ExtractNodes (MVP)**
- `POST /analyze/extract` exists in `backend/app/routers/analyze.py` (line 77).
- IMPORTANT: `analyze.py` uses `extract_nodes_from_text` from `utils/node_extract.py` (heuristic),
  NOT from `services/node_extractor.py` (which has NER/heuristic providers).
- `services/node_extractor.py` is untracked (`??` in git status) -- richer provider is not wired
  to the analyze endpoints. The `NODE_EXTRACTOR` env var has no effect on `/analyze/extract` or `/analyze/content`.

**S5 -- Multi-label Bloom classification (MVP)**
- `POST /analyze/classify` returns `prob_vector` and `top_levels`.
- `services/bloom_multilabel.py` implements hybrid keyword+LLM classifier, is untracked in git.
- `.env` sets `BLOOM_CLASSIFIER=llm` -- LLM path will be used if `OPENAI_API_KEY` is set.
- `data/bloom_verbs_ru.json` exists (untracked), used as keyword glossary fallback.
- LLM provider: Groq (`llama-3.3-70b-versatile`) via OpenAI-compatible API.

**S6 -- Endpoint "Content Analysis"**
- `POST /analyze/content` in `backend/app/routers/analyze.py` (line 105).
- Pipeline: extract -> classify -> persist to `knowledge_nodes` -> embed with `embed_texts`.
- Embedding dim guard (must be 1536) added in current branch.
- BUG: classifier is called once for the FULL text, not per-node. All nodes get the same
  `prob_vector`. This is a semantic inaccuracy (see Bugs section).

**S7 -- Node embeddings**
- `services/embedding_provider.py` (untracked) implements 4 providers: hash, local (sentence-transformers), openai, random.
- Active provider: `EMBEDDING_PROVIDER=hash` per `.env`. HashingProvider uses term-frequency hashing (deterministic, offline, non-semantic).
- `GET /nodes/search` uses pgvector cosine distance; vec IS NOT NULL guard added.
- `services/embedding.py` delegates to `embedding_provider.get_embedding_provider()`.

**S8 -- Knowledge graph edges**
- `GET /graph` returns nodes + edges (similarity + co-occurrence). Only one route handler in graph.py.
- Celery task `rebuild_graph_edges` in `backend/app/tasks/tasks.py` (line 130) -- persists edges to `knowledge_edges`.
- BUG: `POST /graph/rebuild` is NOT in `graph.py`. Frontend calls `/graph/rebuild` (line 297 of index.tsx),
  but the route does not exist. This call returns 404/405. See Bugs section.

**S9 -- UI: "Content Analysis" tab**
- Text input, file load, analyze button -> `/analyze/content`, node table, JSON/CSV export.
- All functionality implemented in `frontend/pages/index.tsx`.

**S10 -- UI: "Knowledge Graph" tab**
- Interactive graph via Cytoscape.js in `frontend/components/GraphView.tsx`.
- Color-coding by argmax Bloom level, gradient border for multi-label (secondary level >= threshold).
- Hover card, filter by Bloom level, zoom, export PNG.
- Loads from `GET /graph`.
- Filters by dataset_id, top_k, min_score, include_cooccurrence, limit_nodes.

**S11 -- Quality metrics**
- Hamming Loss, F1 micro/macro implemented in `backend/app/routers/evaluate.py` (`GET /evaluate/multilabel`).
- Router is registered in `main.py` (line 37).
- Standalone script: `scripts/evaluate_multilabel.py`.

**S12 -- Defense materials**
- `docs/DEFENSE_MATERIALS.md`, `docs/DEMO_EXAMPLES.md` exist.

**fix/tz-vector-guards (current branch, not yet merged to main)**
- `graph.py`: `kn.vec IS NOT NULL` guard on node query (raw SQL).
- `nodes.py` (`/nodes/search`): `kn.vec IS NOT NULL` + dim validation.
- `analyze.py` (`/analyze/content`): dim validation guard (HTTP 400).

---

## Bugs Found (Full Source Audit 2026-03-03)

### CRITICAL: BUG-1 -- `GET /nodes/search` is shadowed by `GET /nodes/{node_id}`
- **File**: `backend/app/routers/nodes.py`, lines 69 and 115.
- **Problem**: FastAPI registers routes in declaration order. `GET /nodes/{node_id}` (line 69)
  is declared before `GET /nodes/search` (line 115). When a request for `/nodes/search` arrives,
  FastAPI matches `{node_id}="search"`, attempts `db.get(KnowledgeNode, "search")`, and returns 404
  (or a 422 if SQLAlchemy rejects the non-integer). The `/search` endpoint is effectively unreachable.
- **Fix needed**: Move `@router.get("/search", ...)` to BEFORE `@router.get("/{node_id}", ...)`.

### CRITICAL: BUG-2 -- `POST /graph/rebuild` route is missing
- **File**: `backend/app/routers/graph.py` has only ONE route handler: `GET /graph` (line 25).
  There is no `POST /graph/rebuild` endpoint in the router.
- **Problem**: Frontend (`frontend/pages/index.tsx`, line 297) calls `POST /graph/rebuild` with a
  JSON body. Celery task `rebuild_graph_edges` exists and is wired in `queue.py`. But there is no
  HTTP endpoint to trigger it. All frontend "Rebuild Graph" button calls return 404/405.
  The `GraphRebuildIn` and `GraphRebuildOut` schemas exist in `schemas.py` (lines 260-271) but are
  not used by any router.
- **Fix needed**: Add `@router.post("/rebuild", response_model=GraphRebuildOut)` to `graph.py`.

### CRITICAL: BUG-3 -- `PUT /nodes/{node_id}/labels` route is missing
- **Problem**: Frontend (`frontend/pages/index.tsx`, line 346) calls `PUT /nodes/{node.id}/labels`
  to save human labels from the labeling UI. This endpoint does not exist in `nodes.py` or any other
  router. `NodeLabelsIn` and `NodeLabelsOut` schemas exist in `schemas.py` but are not used.
  The entire labeling workflow (tab "Разметка" in UI) is broken -- the save action always 404s.
- **Fix needed**: Add `@router.put("/{node_id}/labels", response_model=NodeLabelsOut)` to `nodes.py`
  that writes to `node_labels` table.

### NON-CRITICAL: BUG-4 -- Classifier called once for full text, all nodes get same prob_vector
- **File**: `backend/app/routers/analyze.py`, lines 124-133.
- **Problem**: `classify_bloom_multilabel(payload.text, ...)` is called with the full source text,
  and its result is reused for every extracted node. All nodes receive identical `prob_vector` and
  `top_levels`, regardless of the node's actual title or context. This defeats the purpose of
  per-node classification.
- **Fix needed**: Call `classify_bloom_multilabel(node["context_snippet"] or node["title"], ...)` per node.

### NON-CRITICAL: BUG-5 -- `NODE_EXTRACTOR` env var has no effect on analyze endpoints
- **File**: `backend/app/routers/analyze.py`, lines 25 and 107.
- **Problem**: `analyze.py` imports `extract_nodes_from_text` directly from `utils/node_extract.py`
  (the bare heuristic function). The pluggable `services/node_extractor.py` with `get_node_extractor()`
  (which respects `NODE_EXTRACTOR=local_ner`) is never called by the analyze endpoints.
  Setting `NODE_EXTRACTOR=local_ner` in `.env` does nothing for `/analyze/extract` or `/analyze/content`.
- **Fix needed**: In `analyze.py`, replace `from ..utils.node_extract import extract_nodes_from_text`
  with `from ..services.node_extractor import extract_nodes` and use it in both endpoints.

### NON-CRITICAL: BUG-6 -- `context_snippet` is empty for most nodes (regex bug in node_extract.py)
- **File**: `backend/app/utils/node_extract.py`, line 59.
- **Problem**: The regex pattern is `rf"\\b{re.escape(tok)}\\b"` (double-escaped backslash).
  In a raw f-string, `\\b` becomes the literal two characters `\b`, not the word-boundary assertion.
  The regex `\\bword\\b` will never match anything in normal text, so `context` is always `""` for
  all keyword-type nodes. Only `proper_noun` nodes get a context snippet via the preceding loop.
- **Fix needed**: Change `rf"\\b{re.escape(tok)}\\b"` to `rf"\b{re.escape(tok)}\b"`.

### NON-CRITICAL: BUG-7 -- `.env` contains a real API key committed to git
- **File**: `backend/.env`, line 32.
- **Problem**: `OPENAI_API_KEY` contained a live Groq API key in plaintext. If this repo is pushed
  to GitHub (even private), the key is exposed. Groq may automatically revoke keys found in public repos.
- **Fix needed**: Rotate the key immediately. Add `backend/.env` to `.gitignore`.

---

## Pending (MVP Requirements)

None -- all 13 steps are done per the plan.

---

## Blocked

None at the plan level. BUG-1, BUG-2, BUG-3 block specific features in runtime.

---

## Enhancement Opportunities (Beyond MVP)

**E1 -- Wire `NODE_EXTRACTOR` provider to analyze endpoints (Easy, high value)**
- `services/node_extractor.py` has NatashaNerExtractor (proper NER with sentence offsets) already
  implemented but not connected to `/analyze/extract` or `/analyze/content`.
- Fixes BUG-5 and delivers real NER quality improvement simultaneously.

**E2 -- Real LLM-based Bloom classification (Medium)**
- `BLOOM_CLASSIFIER=llm` is already set in `.env`. Groq key is configured.
- Just fixing BUG-4 (per-node classify call) will enable true per-node LLM classification.
- Value: significantly better `prob_vector` accuracy, measurable F1 improvement.

**E3 -- Real semantic embeddings via sentence-transformers (Easy/Medium)**
- `EMBEDDING_PROVIDER=hash` is active. Change to `local` with `intfloat/multilingual-e5-small`
  (already configured in `.env` as `EMBEDDING_MODEL_LOCAL`).
- Requires `sentence-transformers` installed in Docker image (check requirements.txt).
- Value: `/nodes/search` and `/graph` return semantically meaningful nearest neighbors.

**E4 -- Desktop (.exe) packaging with Tauri (Hard)**
- TZ mentions Windows .exe as preferred delivery. Not done. Docker is the current delivery.
- Value: teachers run without Docker or CLI setup.

**E5 -- Export JSONL of labeled nodes (Easy)**
- `GET /datasets/{id}/labeling/export` is implemented in `labeling.py` and registered in `main.py`.
- Only missing: a UI button to call it. The backend is ready.

---

## Work Log

### 2026-03-03 -- Full Source Audit
- Read all key source files: routers (analyze, nodes, graph, labeling, evaluate, datasets),
  services (bloom_multilabel, embedding_provider, embedding, node_extractor),
  models, schemas, migrations, Celery tasks, docker-compose, .env, frontend index.tsx, GraphView.tsx.
- Confirmed: all 13 MVP steps are implemented in code, not just marked done.
- Found 3 critical bugs: /nodes/search shadowed, POST /graph/rebuild missing, PUT /nodes/{id}/labels missing.
- Found 4 non-critical bugs: single classify call for all nodes, NODE_EXTRACTOR not wired, context_snippet regex broken, API key in .env.
- Updated PROGRESS.md with full bug inventory.

### 2026-03-03 -- Session 1
- PROGRESS.md created for the first time.
- Assessed full project state after sprint S0-S12 + fix/tz-vector-guards branch.
- All 13 MVP steps confirmed done (at plan level).
- fix/tz-vector-guards: 1 commit ahead of main, not yet merged.

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

---

## Next Steps (Priority Order)

1. **Fix BUG-1** -- Move `GET /nodes/search` before `GET /nodes/{node_id}` in `nodes.py`.
   One-line reorder, zero risk.

2. **Fix BUG-2** -- Add `POST /graph/rebuild` route to `graph.py`. Schema already exists
   (`GraphRebuildIn`/`GraphRebuildOut`). Creates Job, calls `enqueue_or_mark`. ~15 lines.

3. **Fix BUG-3** -- Add `PUT /nodes/{node_id}/labels` to `nodes.py`. Writes to `node_labels`
   (upsert by `node_id` + `annotator`). Unblocks labeling tab entirely.

4. **Fix BUG-6** -- Fix the regex in `utils/node_extract.py` line 59: `\\b` -> `\b`.
   Restores context_snippet for keyword nodes, improves classification quality.

5. **Fix BUG-5 + E1** -- Wire `services/node_extractor.get_node_extractor()` into `analyze.py`.
   Activates NER pipeline, respects `NODE_EXTRACTOR` env var. Resolves both BUG-5 and E1.

6. **Fix BUG-4** -- Call classifier per-node with node context instead of full text.
   This gives each node a meaningful and distinct `prob_vector`.

7. **Rotate API key (BUG-7)** -- Revoke Groq key, generate new one, add `.env` to `.gitignore`.

8. **Merge fix/tz-vector-guards into main** -- Critical NULL-vector guards are not in main yet.
