# B05 Instructor agent and reviewable course actions

Status: complete

## User outcome

An instructor opens the assistant from the exact Canvas course, sees a bounded
evidence-backed course priority, inspects the supporting finding, and prepares
an editable improvement draft with a read-only Canvas change preview. Nothing
is accepted or written to Canvas without a separate explicit human action.

## Users and permissions

- Instructor: use only instructor workflows in the exact launched course;
  inspect current-course summaries, audits, findings, cited drafts, and
  read-only change previews; explicitly accept or reject only own-course drafts.
- Student and all other roles: cannot enumerate or execute this instructor
  surface or its artifacts through the agent route.
- Anonymous, expired/revoked, compatibility bypass, wrong-course,
  cross-organization, and inactive membership contexts receive non-disclosing
  denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B05.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- `development/specs/done/B04-learner-agent-canvas-course.md`.
- Existing `teacher_workspace`, course audit, course Copilot, finding review,
  and Canvas change-set services.
- Workshop Route in `development/design/DESIGN_SYSTEM.md`.

## Scope

- Bind `instructor.course_summary.v1`, `instructor.inspect_audit.v1`,
  `instructor.draft_improvement.v1`, and
  `instructor.preview_canvas_change.v1` to strict typed adapters.
- Extract a bounded finding-evidence application service rather than calling a
  FastAPI router from a tool.
- Reuse existing authoritative audit, Copilot draft, review, and read-only
  change-set services; do not create parallel domain logic.
- Add the instructor assistant to the exact signed Canvas course flow.
- Preserve editable drafts and explicit accept/reject review decisions.

## Non-goals

- Canvas writes, grading, roster, submissions, gradebook, generic search, or
  arbitrary model/database/network tools.
- Learner transcript inspection or individual learner ranking.
- Aggregate question-gap workflow (B06), program/admin tools (B07), real school
  Canvas, deployment, or production model-host validation.

## User flow

1. Instructor launches the protected workspace from the exact Canvas course.
2. The assistant shows a bounded current-course summary and one review priority.
3. The instructor opens its evidence and requests an improvement draft.
4. The draft exposes citations, confidence, limitations, and `draft` review
   status in an editable field.
5. Accept/reject is a separate CSRF-protected human action; accepted drafts can
   be inspected as a read-only Canvas change preview.

## UX contract

- Single job: move from one course priority to one reviewable cited draft.
- Continue Workshop Route tokens and typography. The signature element is a
  red-pencil review thread connecting finding, evidence, and draft; it encodes
  state and is not decorative.
- Desktop uses a calm course context plus a focused review sheet. Mobile stacks
  summary, evidence, and draft in that order with no horizontal overflow.
- No provider, model, RAG, tool, endpoint, or integration terminology.
- Loading, no-audit, no-finding, low-confidence, insufficient-evidence, failed,
  permission, stale-artifact, draft, accepted, rejected, and preview-only states
  are distinct, keyboard reachable, and announced appropriately.
- Primary labels: `Проверить приоритет`, `Подготовить черновик`,
  `Принять после проверки`, `Отклонить`, `Показать изменения для Canvas`.

## Data and API

- Preserve `agent.v1` and the frozen B03 instructor workflow/tool names.
- Use strict closed input/output DTOs, absolute time/output/step budgets,
  execution-time authorization, and content-free per-tool audit recovery from
  B04.
- Generic `AgentRun` stores opaque refs only; draft content remains in
  `CourseCopilotSuggestion` under its existing retention/review model.
- Human review remains a direct version-aware endpoint outside the model tool
  registry. Canvas change set remains a read-only projection.

## Security and privacy

- Recheck session, registration, organization, course, instructor membership,
  audit/finding/draft ownership, and current resource state before every tool.
- Treat course content, finding evidence, instruction text, and generated output
  as untrusted. Validate cited chunks/documents independently.
- Never expose expected answers, hidden credentials, raw learner questions,
  model metadata, or arbitrary Canvas URLs.
- A model cannot accept/reject its own draft or apply a Canvas change.

## Acceptance criteria

- [x] A signed instructor completes summary -> finding evidence -> cited draft
  -> explicit review -> read-only change preview in the exact course.
- [x] Every tool enforces strict DTOs, current authorization, evidence/output
  bounds, absolute deadline, and content-free audit events.
- [x] Student, wrong-course, expired/revoked, stale finding/draft, and
  cross-organization cases fail without revealing instructor artifacts.
- [x] Drafts always expose evidence, confidence, limitations, and review state;
  unsupported drafts fail closed or clearly request more evidence.
- [x] No model output is accepted and no Canvas operation is applied without a
  separate explicit human action.
- [x] Desktop/mobile, keyboard/focus, loading, empty, failure, permission,
  low-confidence, stale, accepted, rejected, and preview states pass.
- [x] Full regressions and product-UX, RAG/safety, and batch-quality reviews have
  no open P0/P1 findings.

## Test plan

- Unit: instructor DTOs, finding evidence membership, citation validation,
  deadlines, audit recovery, review transition rules, and preview bounds.
- Service/API: exact role/course/session, all negative roles, stale artifacts,
  idempotency, no raw content in run/audit metadata, and separate CSRF review.
- RAG: supported/unsupported drafts, injection-shaped evidence, citation
  support, deterministic fallback, and no expected-answer leakage.
- Browser: signed instructor launch through summary, evidence, draft, review,
  preview, loading, empty, error, permission, mobile, focus, and overflow.
- Regression: full pytest, strict benchmark, frontend lint/build, repo-wide
  pre-commit, and diff check.

## Batch review

Completed 2026-08-03.

- The signed simulator completes summary, evidence inspection, cited draft,
  version-aware review, and read-only Canvas preview on desktop and mobile.
- Opaque draft references bind the exact organization, course, instructor,
  product session, current audit, confirmed finding, current citations, and
  optimistic review version. Stale and concurrent states fail closed.
- The default deterministic draft path passed the committed eight-case RU/EN
  instructor safety protocol with 1.0 safety accuracy and zero answer leakage.
  External generative drafts remain disabled unless explicitly opted in and are
  not claimed as production-validated.
- Final evidence: 389 backend tests, frontend lint/build, targeted desktop/mobile
  signed-launch Playwright checks, repo-wide pre-commit, `git diff --check`, and
  batch-quality, product-UX, and RAG/safety rechecks with no remaining P0/P1.
- No school Canvas, Canvas API, organization model host, deployment, or Canvas
  mutation was used.
