# Online Codex continuation handoff

> Historical handoff from 2026-08-02. Its publication gate, active spec, and
> next-outcome instructions are superseded by `AURUS_HANDOFF.md` and the current
> `development/STATUS.md`. Do not repeat the completed simulator work below.

Snapshot date: 2026-08-02
Active milestone: M05 Canvas Letovo embedded course companion
Local branch: `J-D-polish-ui-and-stability`
Local base commit: `b017a01 Add roadmap for quality, UX, and production hardening`

## Continuation gate

This snapshot is not yet available from GitHub. At handoff preparation time the
working tree contained 270 changed paths: 85 tracked modifications and 185
untracked paths. Many M01-M05 foundations are untracked, so publishing only the
last course-map files would create a broken online checkout.

Do not start implementation in an online session until the intended repository
snapshot has been reviewed, committed, and pushed. A live `git fetch` was not
available during preparation because the local proxy endpoint was unreachable;
the cached remote-tracking ref reported no ahead/behind commits, but that is not
proof that GitHub is current.

Never publish `.env`, `.env.local`, `.claude/`, `.playwright-cli/`,
`.playwright-mcp/`, `output/`, credentials, browser sessions, or real Canvas
content. The ignore rules cover these local artifacts.

## Read first

Read these files in order and do not load all project documents up front:

1. `AGENTS.md`
2. `development/specs/active/M05-letovo-embedded-course-companion.md`
3. `development/STATUS.md`, especially `Current batch`, `Next batch`, and
   `External blockers`
4. This handoff
5. Only the implementation files named in the next-outcome section

If those sources disagree, stop and report the conflict before editing.

## Product goal

Build a direct, useful Canvas companion that feels native to a Canvas Letovo
user. The learner sees the exact launched course and its familiar ordered
structure, can continue from a material, and can ask for cited help inside the
Canvas frame. Teachers retain the exact-course workspace. The product must not
become a generic RAG engineering dashboard or an administrative surveillance
tool.

The official school Canvas remains disconnected. Use synthetic users, courses,
content, registrations, and local/self-hosted test Canvas instances only.

## Implemented and verified

- Exact signed learner product session and read-only `GET /course-map` boundary.
- Bounded published/available topology with ordered modules and items.
- Fail-closed handling for wrong role/course/session, removed modules, locks,
  prerequisites, malformed or credential-shaped URLs, and unknown item types.
- Learner LTI launch redirects to `/canvas-companion` without course selection.
- The companion validates the selected module through the course map and passes
  `module_id` into the protected module-scoped tutor retrieval flow.
- Local Canvas-like simulator with two synthetic course shapes and a
  server-only, production-disabled registration map for signed launch frames.
- Workshop Route styling, desktop/mobile responsive behavior, keyboard focus,
  reduced motion, explicit external links, evidence, confidence, and safe
  failure states.

Last recorded quality evidence:

- Full backend suite reached 300 passing tests before the final narrow URL and
  publication hardening; 51 focused Canvas/LTI/tutor tests passed afterward.
- Frontend lint and production build passed.
- Repo-wide pre-commit and `git diff --check` passed.
- Protected companion browser checks passed at 1440 x 900 and 390 x 844 with a
  clean console, no horizontal overflow, and a verified module-scoped handoff.
- General, product/UX, and RAG/isolation reviews found no remaining P0/P1.

Treat these as prior evidence, not as a substitute for rerunning relevant gates
after the online checkout is created.

## Exact next outcome

Finish the remaining local acceptance gate in the active spec:

1. Add a deterministic development bootstrap that creates one synthetic LTI
   registration and exact binding for each simulator course: `demo-ai` and
   `demo-review`.
2. Keep the bootstrap development-only, idempotent, secret-free, and impossible
   to enable in production.
3. Automate this matrix for both fixtures:

   `simulator dashboard -> exact course -> signed learner launch -> embedded
   companion -> selected module -> module-scoped tutor`

4. Cover desktop 1440 x 900 and mobile 390 x 844, keyboard navigation, clean
   console, no horizontal overflow, exact course identity, source return, and
   the bounded loading/access/error/unsupported states in the active spec.
5. Run focused tests during implementation. At batch close run the full backend
   suite, frontend lint/build, repo-wide pre-commit, and `git diff --check`.
6. Use the reviewers from `development/agents/` only at the batch boundary:
   general, product/UX, and RAG/isolation.
7. Fix P0/P1 findings, perform one targeted recheck, and update
   `development/STATUS.md` once.

Start inspection with:

- `backend/app/services/lti_development.py`
- `backend/app/services/lti_registration.py`
- `backend/app/services/lti_binding.py`
- `backend/app/routers/lti.py`
- `backend/app/routers/course_map.py`
- `frontend/lib/canvas-simulator-server.ts`
- `frontend/pages/canvas-simulator/courses/[courseId].tsx`
- `frontend/pages/canvas-companion.tsx`
- `tests/test_lti_launch.py`
- `tests/test_course_map.py`

Do not redesign the completed companion or reopen completed M01-M05 slices
unless a failing acceptance test exposes a concrete regression.

## Environment bootstrap

Use a hosted environment with Python 3.11+, Node.js 18.18+, npm, and optionally
Docker. From the repository root:

```bash
bash scripts/setup-online-codex.sh
```

This installs the backend plus test tooling from `requirements-dev.txt` and the
locked frontend packages with `npm ci`. To create missing ignored development
environment files from the committed secret-free examples:

```bash
bash scripts/setup-online-codex.sh --with-env
```

For the simulator, set these server-side frontend variables in the online
environment, never in committed files:

```text
APP_ENV=development
CANVAS_SIMULATOR_ENABLED=true
CANVAS_SIMULATOR_DATA_MODE=synthetic
CANVAS_SIMULATOR_LTI_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

The registration IDs must be produced by the deterministic bootstrap requested
above; do not hard-code guessed database IDs into source code.

## Commands

Focused backend work:

```bash
python -m pytest -q tests/test_lti_launch.py tests/test_course_map.py tests/test_canvas_import.py tests/test_student_tutor.py
```

Batch close:

```bash
python -m pytest -q
npm --prefix frontend run lint
npm --prefix frontend run build
pre-commit run --all-files
git diff --check
```

Optional full local stack after copying environment examples:

```bash
docker compose up --build
```

## Hard boundaries

- No access to or mutation of `canvas.letovo.ru`.
- No school credentials, cookies, Developer Keys, course files, or copied HTML.
- No Canvas writes, grades, submissions, messages, or roster access.
- No deployment to the organization agent host.
- No cross-course data access and no course ID chosen from a learner URL.
- No answer-only student experience; prefer explanation, hints, citations, and
  abstention when evidence is insufficient.
- No commit, push, deployment, or external publication unless the user asks.

After the local matrix passes, the next integration gate is a separate clean
self-hosted Canvas instance with synthetic users and courses. It is not part of
the immediate online batch unless the user explicitly expands the scope.
