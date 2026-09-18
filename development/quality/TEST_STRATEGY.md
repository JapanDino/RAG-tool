# Test strategy

## Principles

- Test user-visible risk, not implementation trivia.
- Keep deterministic offline coverage for core acceptance.
- Separate retrieval quality from generation quality.
- Every permission boundary needs positive and negative tests.
- Preserve course and organization isolation in fixtures.
- UI states and browser flows supplement, not replace, backend tests.

## During a batch

Run the smallest relevant checks:

- focused pytest module or test name;
- Python formatting for touched files;
- TypeScript or ESLint check for touched frontend work;
- one manual or browser check of the active user flow.

Do not run the complete quality gate after every edit.

## Batch quality gate

Backend:

    python -m pytest -q
    pre-commit run --all-files

Frontend:

    cd frontend
    npm run lint
    npm run build

UI-heavy batches:

- desktop and mobile screenshots;
- browser console and network failures;
- keyboard-only primary flow;
- loading, empty, error, permission, and low-confidence states;
- long Russian content;
- reduced-motion behavior when motion exists.

## Coverage by risk

### Identity and permissions

- role matrix;
- cross-course and cross-organization denial;
- direct API access;
- audit trail;
- session and token failures.

### RAG and models

- Recall@K and MRR;
- citation integrity;
- unsupported-question refusal;
- prompt-injection fixtures;
- model output schema failures;
- latency and fallback.

### Canvas

- pagination and partial endpoint failure;
- idempotent re-import;
- version/content-hash changes;
- SSRF, redirects, internal TLS, and host allow-list;
- role and course-context mapping;
- no write during read-only milestones.

### Frontend

- role-specific navigation;
- evidence and confidence presentation;
- destructive-action confirmation;
- accessible names and visible focus;
- responsive primary flows.

## Evidence

Record exact commands and material limitations in the active spec’s final batch
review. Keep benchmark datasets versioned and hashed when results support a
quality claim.
