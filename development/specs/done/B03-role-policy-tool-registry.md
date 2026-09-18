# B03 RolePolicy, ToolRegistry, and bounded workflow routing

Status: active

## User outcome

An authenticated Canvas user can submit one bounded agent message and receive
either an allowed role-specific workflow plan or a safe unsupported response;
the request cannot change its organization, course, role, tools, or model
settings and does not yet execute tools or change Canvas.

## Users and permissions

- Student: route only learner explanation, assessment-safe hint, self-check,
  source opening, and own-history workflows.
- Instructor: route only course summary, audit/evidence, aggregate question-gap,
  improvement-draft, and change-preview workflows for the launched course.
- Methodologist/program designer: route only approved program-inspection and
  review-note workflows inside an authorized organization/program scope.
- Administrator: route only aggregate operational, integration, policy, and
  retention workflows without transcripts or individual rankings.
- Compatibility bypass, anonymous callers, expired/revoked sessions, and role or
  course mismatches receive non-disclosing denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B03.
- `development/specs/done/B00-agent-contract-freeze.md`.
- `development/specs/done/B02-model-gateway-foundation.md`.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- `development/decisions/ADR-0001-bounded-role-aware-workflows.md` and
  `ADR-0002-execution-time-role-tool-policy.md`.
- Existing identity, LTI product-session, course/program authorization, tutor,
  audit, Copilot, and program services.

## Scope

- Implement immutable `RolePolicy` workflow/tool allow-lists using canonical
  runtime roles and exact server-derived context.
- Implement a typed `ToolRegistry` whose entries point only to the exact
  existing/planned symbols frozen in `agent-tools.v1`.
- Implement deterministic closed-enum workflow routing with one bounded
  clarification path; model-selected routing remains optional and must validate
  through the B02 gateway if introduced.
- Add bounded content-free agent run/route observability only where the frozen
  `agent.v1` contract requires durable state.
- Add the protected versioned message/route API seam and no-store response
  headers without exposing an engineering dashboard.
- Do not execute product tools in this batch; prove policy and routing before
  connecting learner/instructor workflows.

## Non-goals

- Learner or instructor agent UI, streaming conversation, multi-turn memory,
  retrieval/generation, citations, or model quality claims.
- Model-callable deletion, review decisions, Canvas reads/writes, generic
  database/network/shell tools, or user-selected provider/model/prompt.
- Real Canvas, provider, agent-host, deployment, credentials, or production SSO.
- Program/administration UI or research data collection.

## User flow

1. A verified product session or development identity submits a bounded message.
2. The server derives organization, course, user, and canonical role.
3. The router chooses one workflow from the exact role allow-list or returns a
   safe unsupported/clarification state.
4. The response exposes a reviewable product status and no internal prompt,
   chain-of-thought, credential, unrestricted tool name, or hidden resource.

## UX contract

- No new user-facing page is required; API copy must already use product terms
  such as “help with course material” rather than router/tool jargon.
- Loading/events are bounded and no-store if exposed; unsupported requests state
  the next valid action without inventing an answer.
- Permission denials remain non-disclosing; assessment requests route only to
  explanation/hint workflows.
- Any changed UI must follow Workshop Route, desktop/mobile, keyboard, focus,
  reduced-motion, and explicit error/loading/permission state requirements.

## Data and API

- Use `agent.v1` request/response/error/event shapes without accepting trusted
  context fields from the body.
- Every workflow and tool uses a closed enum, version, schema, timeout/output
  limit, role allow-list, and named implementation symbol.
- If `AgentRun`/route metadata is persisted, store content-free scope/status,
  policy/workflow versions, bounded failure class, and timestamps only; do not
  duplicate message text or tutor transcripts.
- Preserve current tutor/Copilot/model APIs and Pages Router architecture.

## Security and privacy

- Resolve and recheck role/resource authorization at routing and future
  execution boundaries; launch-time checks alone are insufficient.
- Reject caller/model-selected organization, course, role, tool, provider,
  origin, credential, model, system prompt, limits, database query, URL, or
  Canvas operation.
- Imported course content and message text are untrusted data and cannot alter
  policy, tool schemas, trusted context, or system instructions.
- Bound message size, clarification count, workflow steps, planned tool count,
  duration, event count/size, and retained metadata.

## Acceptance criteria

- [x] Every canonical role has an exact workflow/tool allow-list matching the
  frozen catalog; no generic or duplicate tool exists.
- [x] Trusted organization/course/user/role are server-derived and cannot be
  changed by message input, prompt injection, or model output.
- [x] Supported messages route to one allowed closed workflow; unsupported and
  ambiguous messages return bounded safe states.
- [x] Student assessment-answer requests cannot route to answer-delivery or any
  instructor/program/administrator workflow.
- [x] Anonymous, compatibility-bypass, expired/revoked, cross-course,
  cross-organization, and every wrong-role request fail non-disclosingly.
- [x] No tool/provider call or Canvas mutation occurs in this planning slice.
- [x] Content-free events/metadata are bounded, secret-safe, and no-store.
- [x] Full regressions and batch-quality, agent-safety, and RAG reviews have no
  open P0/P1 findings.

## Test plan

- Unit: role/workflow/tool matrix, deterministic routing, ambiguity, assessment
  guard, message/event/step budgets, injected control fields, and registry
  symbol/schema validation.
- Service/API: every role allow/deny pair; exact session scope; bypass/anonymous,
  expiry/revocation, cross-course/organization, no-store, and zero tool/model
  transport calls.
- Security: prompt/tool-name/context/provider injection, imported-instruction
  text, oversized input, unknown enum/version, replay, and error redaction.
- Regression: current tutor, Copilot, program, identity, LTI, B02 ModelGateway,
  full pytest, frontend lint/build if changed, pre-commit, and diff check.
- Batch review: quality, agent safety, and RAG evaluator in parallel; product UX
  if any user-facing interface changes.

## Batch review

Complete. Final evidence: 367 backend tests, repo-wide pre-commit, focused
agent/LTI/model regressions, and quality, agent-safety, and RAG targeted
rechecks passed with no remaining P0/P1 findings.

Deferred to execution batches: replace declarative field-name tool schemas with
strict runtime DTO/JSON Schema validation; reconsider `course_id ON DELETE SET
NULL`; add a stable redacted/no-store mapper for unexpected exceptions; add an
auditable receipt for global inactive-organization retention cleanup; enforce a
raw ASGI/proxy request-body cap; and rehearse migration `0040` on PostgreSQL.
