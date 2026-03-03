# Project Progress Tracker

> **TZ Source**: `docs/DEVELOPMENT_PLAN_TZ_BLOOM.md` (+ `docs/PRODUCT_PLAN.md`)
> **Last Updated**: 2026-03-03
> **Overall Progress**: 100% (13/13 core steps done -- MVP complete)

---

## Summary
| Status | Count |
|--------|-------|
| Done | 13 |
| In Progress | 0 |
| Pending | 0 |
| Blocked | 0 |
| Enhancements | 5 |

---

## Completed (MVP Steps S0-S12)

**S0 -- Normalize plan and tracking**
- Single unified plan, status table S0..S12 created in `docs/DEVELOPMENT_PLAN_TZ_BLOOM.md`.

**S1 -- Data contract "node" and "probabilities"**
- `KnowledgeNode` entity defined with `prob_vector[6]`, `top_levels`, `embedding_dim`, `embedding_model`, `version`, `model_info`.
- Bloom levels order fixed: `[remember, understand, apply, analyze, evaluate, create]`.

**S2 -- DB migrations for KnowledgeNode**
- Migrations: `0010_knowledge_nodes.sql`, `0011_knowledge_edges.sql`, `0012_node_labels.sql`, `0013_jobtype_graph.sql`.
- Indexes on `dataset_id`, `vec` (pgvector).

**S3 -- CRUD/API for nodes**
- `POST /nodes`, `GET /nodes`, `GET /nodes/{id}`, `PUT /nodes/{id}`, `DELETE /nodes/{id}`.
- Schemas in `backend/app/schemas/schemas.py`.

**S4 -- ExtractNodes (MVP)**
- `POST /analyze/extract` with `node_type` (`proper_noun`, `keyword`).
- Service: `backend/app/services/node_extractor.py`.

**S5 -- Multi-label Bloom classification (MVP)**
- `POST /analyze/classify` returns `prob_vector` and `top_levels`.
- Bloom verb glossary baseline: `data/bloom_verbs_ru.json`.
- Service: `backend/app/services/bloom_multilabel.py`.

**S6 -- Endpoint "Content Analysis"**
- `POST /analyze/content`: extract -> classify -> persist -> embed in one call.
- Embedding dim validated (must be 1536 -- added in fix/tz-vector-guards).

**S7 -- Node embeddings**
- Embedding provider: `backend/app/services/embedding_provider.py`.
- `GET /nodes/search` using pgvector cosine distance.
- Vector guard added in fix/tz-vector-guards: `kn.vec IS NOT NULL` filter + dim validation.

**S8 -- Knowledge graph edges**
- `GET /graph` returns nodes + edges (similarity + co-occurrence).
- `POST /graph/rebuild` enqueues async job (JobType.graph).
- Edges stored in `knowledge_edges` table.
- Guard added in fix/tz-vector-guards: `kn.vec IS NOT NULL` on node selection query.

**S9 -- UI: "Content Analysis" tab**
- Text/file input, node table, JSON/CSV export.
- Component in `frontend/pages/index.tsx`.

**S10 -- UI: "Knowledge Graph" tab**
- Interactive graph built from `/graph` API (not mock data).
- Color-coding by argmax, gradient for multi-label, filters, zoom.
- Component: `frontend/components/GraphView.tsx`.

**S11 -- Quality metrics**
- Hamming Loss, F1 micro/macro computed.
- Script: `scripts/evaluate_multilabel.py`.
- Dataset: `data/bloom_dataset.jsonl` (>= 100 examples).

**S12 -- Defense materials**
- Launch instructions, demo examples, DB dump guide.
- Files: `docs/DEFENSE_MATERIALS.md`, `docs/DEMO_EXAMPLES.md`.

**fix/tz-vector-guards (current branch, not yet merged to main)**
- `graph.py`: rewrote node query to use raw SQL with `kn.vec IS NOT NULL` -- prevents pgvector crash on NULL vectors.
- `nodes.py` (`/nodes/search`): added `kn.vec IS NOT NULL` filter + `dim != 1536` guard (HTTP 400).
- `analyze.py` (`/analyze/content`): added `embedding_dim != 1536` guard (HTTP 400).
- `docs/DEVELOPMENT_PLAN_TZ_BLOOM.md`: updated history entry.

---

## Pending (MVP Requirements)

None -- all 13 steps are done per the plan.

---

## Blocked

None.

---

## Enhancement Opportunities (Beyond MVP)

**E1 -- Semantic NER instead of heuristic extraction (Medium)**
- Current extractor is keyword/regex-based. Replace with spaCy/ruBERT NER for proper semantic chunking.
- Value: higher-quality node extraction, better graph structure.

**E2 -- Real LLM-based Bloom classification (Medium)**
- Current classifier uses the verb-glossary heuristic baseline. Wire up the `openai` provider (already scaffolded via `ENABLE_LLM=1` env flag).
- Value: significantly better `prob_vector` accuracy, measurable F1 improvement.

**E3 -- Validated real embeddings (Easy/Medium)**
- `embedding_provider.py` exists but current storage is dim=1536 hard-coded (placeholder). Validate end-to-end with a real sentence-transformers model and pgvector.
- Value: `GET /nodes/search` and `GET /graph` return semantically meaningful results.

**E4 -- Desktop (.exe) packaging with Tauri (Hard)**
- The TZ mentions a Windows .exe delivery as the preferred distribution. Not yet done.
- Value: teachers can run without Docker or CLI setup.

**E5 -- Labeling UI endpoint (`/labeling`) (Easy)**
- `backend/app/routers/labeling.py` and `evaluate.py` exist as untracked files -- not wired into the main app.
- Value: enables manual correction/review of Bloom labels directly in the UI.

---

## Work Log

### 2026-03-03
- PROGRESS.md created for the first time.
- Assessed full project state after sprint S0-S12 + fix/tz-vector-guards branch.
- All 13 MVP steps confirmed done.
- fix/tz-vector-guards: 1 commit ahead of main, not yet merged (4 files, +33/-9 lines).
- Untracked files identified: `evaluate.py`, `labeling.py`, `bloom_multilabel.py`, `embedding_provider.py`, `node_extractor.py` -- likely part of S4/S5/S7 work not yet committed to main.

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

## Next Steps

1. **Merge fix/tz-vector-guards into main** -- the vector guard fixes are critical for production correctness (prevents pgvector crashes on NULL vec). PR is 1 commit, clean diff, ready to merge.

2. **Wire up untracked routers** -- `backend/app/routers/evaluate.py` and `backend/app/routers/labeling.py` are not registered in `main.py`. Decide: commit as-is, integrate, or remove to keep the repo clean.

3. **End-to-end smoke test with real embeddings** -- run `scripts/smoke_stage3.sh` after enabling `ENABLE_LLM=0` with a real embedding model to verify `/nodes/search` and `/graph` return non-trivial results.

4. **Enable LLM classification for quality evaluation** -- set `ENABLE_LLM=1`, `LLM_PROVIDER=openai`, re-run `scripts/evaluate_multilabel.py` to get a real F1 baseline against the heuristic.

5. **Commit untracked service files** -- `bloom_multilabel.py`, `embedding_provider.py`, `node_extractor.py` appear in `git status` as untracked. Confirm they are intentionally unversioned or stage them.
