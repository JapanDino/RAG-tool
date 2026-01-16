## Project status (sync with plan)

Main plan: `docs/DEVELOPMENT_PLAN_TZ_BLOOM.md`

Done (code exists):
- Rubrics (CRUD + migrations + seeds)
- Annotation management API (CRUD)
- Validation + fallback
- Quality metrics + stats endpoint
- LLM provider abstraction (heuristic/openai)

Next (recommended):
- C1/D1 MVP from the plan: “text → nodes → Bloom multi‑label probabilities”
- Graph API + basic graph UI
- Desktop packaging track (.exe)

---

Next steps to run later:
1) Apply migration:
   psql -U rag -d rag_db -f backend/migrations/0001_init.sql
   psql -U rag -d rag_db -f backend/migrations/0002_vector_indexes.sql
   psql -U rag -d rag_db -f backend/migrations/0003_constraints.sql
   psql -U rag -d rag_db -f backend/migrations/0004_job_task_id.sql
   # или одной командой:
   ./scripts/apply_migrations.sh
2) Backend env (backend/.env):
   DATABASE_URL=postgresql+psycopg2://rag:rag_pass@localhost:5432/rag_db
   REDIS_URL=redis://localhost:6379/0
   ENABLE_CELERY=1
   # LLM-аннотация (по умолчанию выключена):
   ENABLE_LLM=0
   LLM_PROVIDER=heuristic   # noop|heuristic|openai
   LLM_MODEL=gpt-4o-mini    # для openai-провайдера
   OPENAI_API_KEY=sk-...    # требуется только для LLM_PROVIDER=openai
3) Run API:
   uvicorn backend.app.main:app --reload --port 8000
4) Frontend:
   cd frontend && echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local && npm i && npm run dev
5) Celery worker (when ready):
   celery -A backend.app.tasks.celery_app.celery_app worker -l INFO
6) Smoke test (no LLM, placeholder embeddings):
   ./scripts/smoke_stage3.sh

Status endpoint:
   GET /datasets/{id}/status
6) Later: replace placeholder embeddings + improve search (<->) and add real LLM for annotate.

Notes:
- LLM-аннотация: по умолчанию выключена (ENABLE_LLM=0). Для включения:
    backend/.env:
      ENABLE_LLM=1
      LLM_PROVIDER=openai
      LLM_MODEL=gpt-4o-mini
      OPENAI_API_KEY=sk-...
  Без ключа и без включения флага используется эвристика.
