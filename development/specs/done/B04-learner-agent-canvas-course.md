# B04 Learner agent inside the current Canvas course

Status: complete

## User outcome

A learner opens the assistant from the current Canvas course, asks one bounded
question, and receives either a cited explanation, an assessment-safe hint, a
self-check, an authoritative source action, or an honest abstention without
reselecting the course or seeing integration terminology.

## Users and permissions

- Student: use learner workflows only inside the exact launched course and
  published/available module scope; view and delete only own history.
- Instructor, methodologist, program designer, administrator: no access through
  this learner route; their agent workflows remain future batches.
- Anonymous, compatibility bypass, expired/revoked, wrong-role, cross-course,
  and cross-organization contexts receive non-disclosing denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B04.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- `development/specs/done/B03-role-policy-tool-registry.md`.
- Existing signed LTI product session, `/course-map`, learner companion,
  `course_qa`, tutor policy/data lifecycle, and B02 ModelGateway.
- Workshop Route in `development/design/DESIGN_SYSTEM.md`.

## Scope

- Bind only the four learner workflows to strict typed adapters with runtime
  input/output validation and execution-time authorization.
- Reuse the current course-map and student-visible retrieval/citation guards;
  do not create a second RAG pipeline.
- Connect `POST /agent/v1/messages` and run polling to the current learner
  companion with bounded progress states.
- Deliver cited explanation, assessment-safe hint, formative self-check,
  source opening, abstention, feedback, and own-history deletion.
- Preserve exact selected-module scope as an opaque server-validated reference.
- Produce desktop/mobile screenshots for normal, hint, self-check, abstention,
  loading, expired/permission, and recovery states.

## Non-goals

- Instructor/program/administrator execution or UI.
- Multi-turn hidden memory, autonomous planning, general web search, arbitrary
  URLs, generic database/network/shell tools, Canvas writes, grading, roster,
  submissions, or expected answers.
- Real school Canvas, production model host, deployment, or research data
  collection.

## User flow

1. Learner launches the companion from the exact Canvas course.
2. The page shows the current course/module context and a small set of familiar
   actions: ask for an explanation, get a hint, or check understanding.
3. The server validates the message, session, role, module, workflow, tool
   arguments, evidence visibility, and budgets at execution time.
4. The page progressively shows product-language status, then a cited response,
   source action, self-check, or honest abstention with a recovery action.
5. Feedback and own-history deletion remain explicit human actions with CSRF.

## UX contract

- Keep the assistant inside the Canvas-familiar Workshop Route companion; no
  engineering dashboard, provider selector, model name, tool name, or RAG jargon.
- One primary input and at most three starter actions; do not force course
  reselection after a valid launch.
- Evidence shows a short title/excerpt and “Открыть источник в Canvas” only for
  validated destinations. Confidence uses plain support language.
- Loading, queued, routing, generating, abstained, failed, expired, permission,
  deleted-history, and retry states are distinct and keyboard reachable.
- Mobile iframe width 390 px has no horizontal overflow; controls target 44 px,
  visible focus, live status announcements, and reduced-motion support.

## Data and API

- Preserve `agent.v1`; add strict DTO/JSON Schema types behind the frozen
  learner tool definitions before registering any callable adapter.
- Add bounded run/event transitions without storing raw generic message,
  response, prompt, excerpt, or transcript in `AgentRun`.
- Reuse owned `CourseQuestionAnswer` for learner content/history and its
  effective tutor retention/deletion policy.
- Validate server-issued module/evidence/destination refs against the exact
  user, course, role, visibility, and current resource state.
- Keep ModelGateway server-owned; no browser-supplied model/provider/prompt.

## Security and privacy

- Recheck product session, registration, organization, user, course membership,
  role, module visibility, and tutor policy before every tool call.
- Assessment-shaped requests can only return explanation/guidance; expected
  answers and hidden/unpublished course content never enter retrieval or output.
- Treat message, course text, retrieved HTML, model output, and tool output as
  untrusted; validate citations and opaque refs independently.
- Enforce raw body, normalized message, tool count, step, timeout, output,
  evidence, event, model, and retention budgets.
- Map unexpected failures to stable redacted no-store errors.

## Acceptance criteria

- [x] A signed learner completes explanation, hint, self-check, and source tasks
  in the exact course without course reselection or integration jargon.
- [x] Every learner tool has executable strict argument/result validation,
  current authorization, timeout/output/evidence bounds, safe failures, and a
  content-free audit event.
- [x] Hidden, unpublished, assessment-answer, stale-ref, cross-module,
  cross-course, wrong-role, anonymous, expired, and revoked cases fail safely.
- [x] Citations are membership-validated and abstention is used when evidence is
  insufficient; no unsupported answer is presented as grounded.
- [x] Feedback and own-history deletion remain owner-only explicit actions and
  remove linked learner content plus AgentRun references.
- [x] Desktop/mobile UI covers normal and edge states with clean console,
  keyboard/focus, reduced motion, and zero 390 px overflow.
- [x] Full regressions and product-UX, RAG, agent-safety, and batch-quality
  reviews have no open P0/P1 findings.

## Test plan

- Unit: typed tool schemas, assessment guard, self-check constraints, citation
  membership, ref expiry, budgets, failure mapping, and prompt/output injection.
- Service/API: exact session/module scope, all role denies, CSRF, idempotency,
  provider/fallback behavior, event transitions, deletion, and no raw content in
  generic run/audit metadata.
- RAG evaluation: supported/unsupported, assessment, injection, citation
  support, abstention, module isolation, latency, and deterministic fallback.
- Browser/E2E: signed learner launch through all required desktop/mobile states,
  keyboard/focus, retry, source action, history deletion, console, and overflow.
- Regression: full pytest, frontend lint/build, repo-wide pre-commit, diff check.

## Batch review

Complete on 2026-08-02. Final evidence: 385 backend tests across four parallel
partitions, strict learner RAG benchmark pass, frontend lint/build,
repo-wide pre-commit, and 26/26 desktop/mobile Playwright scenarios. Product UX,
RAG/safety, and batch-quality targeted rechecks found no remaining P0/P1.
Real PostgreSQL and school Canvas verification remain explicit external gates.
