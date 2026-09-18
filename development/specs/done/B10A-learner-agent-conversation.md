# B10A Learner agent conversation inside Canvas

Status: complete

## User outcome

A learner can ask several questions during one signed Canvas companion session,
see a compact chronological route of the questions, reopen any completed result,
and understand that every turn is independently checked against the current
course rather than answered from hidden conversational memory.

## Users and permissions

- Student: ask only learner workflows in the exact signed course and available
  module scope; view and rate only results produced in the current browser
  session; delete only their own persisted tutor history.
- All other roles and unsigned, expired, revoked, cross-course, or cross-module
  contexts remain outside this route and receive the existing non-disclosing
  boundary.

## Context and evidence

- Current user request: complete all useful offline agent work before school
  Canvas/API/model-host access, with emphasis on chat and administrator setup.
- `development/specs/done/B04-learner-agent-canvas-course.md` established the
  strict learner tools and single-run companion.
- `development/agent/API_CONTRACT.md` defines `conversation_id` as grouping,
  not automatic prompt memory.
- `development/design/DESIGN_SYSTEM.md` and `development/design/EXPERIENCE.md`
  define the Workshop Course Route and focused student desk.

## Scope

- Reuse one server-issued `conversation_id` for subsequent requests in the
  current companion session.
- Keep a bounded, browser-memory-only list of completed turns with question,
  selected module/material, agent outcome, and per-turn feedback state.
- Let the learner reopen a prior turn without duplicating full answers on the
  page and without losing the current material selection.
- Make the independent-grounding boundary explicit in plain language.
- Preserve the existing progress, retry, abstention, evidence, source action,
  feedback, history deletion, and signed-session failure behavior.
- Add focused browser coverage for conversation grouping and turn reopening.

## Non-goals

- Hidden multi-turn prompt memory, transcript replay into a model, autonomous
  planning, unrestricted chat, or cross-course conversation.
- Persisting a new generic transcript or changing the agent-run storage model.
- Administrator settings, model-host compatibility, real Canvas, deployment,
  or research data collection; those are subsequent offline batches.

## User flow

1. Learner launches the exact course companion and selects a material.
2. Learner asks a question or uses a bounded quick action.
3. The familiar route shows submission, authorization, evidence lookup, and a
   completed grounded result.
4. The completed turn appears in a compact session thread; a later question is
   grouped into the same conversation but is independently grounded.
5. Learner can reopen a prior turn, rate it, or explicitly delete all owned
   persisted tutor history.

## UX contract

- The course map remains visible and the conversation workbench becomes the
  stronger desktop column; mobile keeps one stacked flow without overflow.
- Use the Workshop Route palette already present: ink `#15315f`, route blue
  `#2457d6`, mint `#83d8c7`, route yellow `#ffd95a`, and apricot `#ff9b73`.
- Display/body/utility roles continue the product typography contract: Segoe UI
  Variable Display, Segoe UI Variable Text, and Cascadia Mono.
- Signature: each compact turn visibly links question, checked course scope,
  and result state instead of imitating generic chat bubbles.
- Loading, empty session, selected turn, failed/retry, abstained, deleted,
  expired, permission, and feedback states remain distinct.
- The interface states: each question is checked anew; previous text is not
  silently sent to the model.
- All turn controls are keyboard reachable, have visible focus, use at least
  44 px targets, announce new results, respect reduced motion, and fit 390 px.
- Primary action remains `Разобраться`.

## Data and API

- No schema or migration change.
- Continue `POST /agent/v1/messages` and the returned execute URL under
  `agent.v1`.
- Capture the accepted server `conversation_id` and send it on later turns.
- Keep at most eight completed turn views in browser memory; raw turns are not
  added to `AgentRun` or content-free audit metadata.
- Existing `CourseQuestionAnswer` ownership, feedback, retention, and deletion
  remain the persistence boundary.

## Security and privacy

- Do not treat `conversation_id` as authorization or model context; every run
  keeps the existing execution-time session, role, course, module, tool, and
  evidence checks.
- Never send previous turn text implicitly in a later request.
- Treat all message, course, evidence, and response text as untrusted React
  content; do not render raw HTML.
- Do not expose provider names, prompts, tool names, credentials, or raw errors.
- Clear the browser-memory conversation on session end and owned-history
  deletion.

## Acceptance criteria

- [x] Two learner requests use one server-issued conversation ID while each
  execute body contains only the current request text and current selection.
- [x] Completed turns form a bounded chronological route and any prior result
  can be reopened with its evidence and per-turn feedback state.
- [x] Changing material hides the expanded result but does not erase the compact
  session route; the next request uses the newly selected module.
- [x] The UI explicitly explains independent grounding and never claims hidden
  conversational memory.
- [x] Expired/permission, failed/retry, abstention, feedback, and history-delete
  behavior remain fail-closed and understandable.
- [x] Desktop/mobile browser checks pass with clean console, keyboard focus,
  reduced-motion behavior, and zero horizontal overflow.

## Test plan

- Frontend lint and production build.
- Playwright: signed learner launch, two-turn conversation ID reuse, current-only
  request bodies, compact thread, reopen prior turn, material change, retry,
  feedback, deletion, expired/permission, desktop/mobile overflow and console.
- Backend focused agent API/learner policy regression only if frontend behavior
  exposes a contract issue.
- Full batch gate and reviewer agents after the vertical slice is complete.

## Batch review

Complete on 2026-08-03. Final evidence: 452 backend tests, repository-wide
pre-commit, frontend lint and production build, 84/84 full Canvas simulator
scenarios, and a post-fix 6/6 desktop/mobile recheck for unsupported content,
immutable failed-turn retry, one-action error recovery, serialized transitions,
and confirmed history deletion. Batch quality, product UX, and agent-safety
targeted rechecks found no remaining P0/P1. Real school Canvas, API, model host,
and deployment remain explicit external gates.
