# B07C Administrator analytics tape

Status: done

## User outcome

An organization administrator opens the existing Canvas connection workspace
and asks whether the assistant is actually being used and whether its model
runtime needs attention. The assistant returns one bounded, read-only comparison
of aggregate adoption, runtime, and estimated cost without exposing people,
courses, messages, prompts, or model/provider identifiers.

## Users and permissions

- Administrator: request the tape for one explicitly selected organization and
  open the existing integration or model-health surface when action is needed.
- Every other role, anonymous, inactive, wrong-organization, and compatibility-
  bypass contexts receive a non-disclosing denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B07.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- Existing content-free `AgentRun` and `ModelInvocationEvent` records.
- Existing signed organization reference from B07B.
- Workshop Route visual and content rules in `development/design/`.

## Scope

- Implement the existing `get_aggregate_adoption_health` and
  `get_agent_latency_cost_health` registry boundaries behind one
  `admin.analytics_health.v1` workflow.
- Compare terminal non-administrator agent runs from the latest 28 days with
  the preceding 28 days.
- Compare organization model invocations from the latest 24 hours with the
  preceding 24 hours.
- Estimate current and previous runtime cost only when both server-owned USD
  token rates are explicitly configured.
- Reuse the signed organization reference and agent state machine; persist only
  the existing content-free result digest.

## Non-goals

- No person, role, workflow, class, course, teacher, or student breakdown; no
  ranking, transcript, prompt, response, grade, submission, or content access.
- No statement that more usage means better learning or that a runtime change
  has a known cause.
- No provider probe, billing integration, budget enforcement, rate write,
  model call, Canvas call, policy change, or infrastructure mutation.
- No research claim or school-production claim in this slice.

## Privacy and metric rules

- Adoption uses terminal runs only and excludes all `admin.*` workflows so the
  analytics request cannot change its own result.
- Current adoption counts are exposed only when the current window contains at
  least five distinct users. Previous-window counts and a direction are exposed
  only when that window independently meets the same threshold.
- When a nonzero window is below threshold, total, completed, abstained, failed,
  and distinct-user counts are all suppressed together; exact low counts cannot
  be inferred from copy, state, or actions. A true zero may be reported as no
  activity because no person is represented by that cell.
- Runtime records are organization-level, content-free infrastructure events.
  An attention state requires at least five calls and either 20% fallback/error
  share or p95 latency of at least eight seconds; otherwise the UI reports facts
  without calling the runtime healthy.
- Cost uses `AGENT_MODEL_INPUT_USD_PER_MILLION_TOKENS` and
  `AGENT_MODEL_OUTPUT_USD_PER_MILLION_TOKENS`. Missing or invalid rates produce
  an honest unconfigured state. Estimates are rounded to USD micros and are not
  presented as invoices.

## User flow

1. The administrator opens the selected organization connection workspace.
2. They choose `Собрать контрольную ленту`.
3. The agent rechecks membership and reads the bounded adoption and runtime
   projections in isolated database scopes.
4. Three tape segments show adoption, runtime, and estimated cost, each with its
   own evidence window, comparison state, and explicit limitation.
5. At most one operational handoff opens the existing integration or model
   section. A missing cost configuration is information, not a fake action.

## UX contract

- Single job: decide whether usage evidence is sufficient and whether runtime
  needs operational attention.
- Continue Workshop Route. Signature element: a continuous `control tape` with
  three perforated segments — adoption, runtime, and cost — comparing `now` with
  the immediately preceding equal window.
- The tape is not a chart dashboard: no score, vanity KPI hero, unexplained
  percentage, traffic-light verdict on people, or decorative data visualization.
- Reuse ink `#15315F`, grid paper `#F8FBFF`, route cobalt `#2457D6`, evidence
  mint `#83D8C7`, marker apricot `#FF9B73`, note yellow `#FFD95A`, and the local
  Segoe/Cascadia stacks. The deliberate risk is a receipt-like continuous strip
  with perforated dividers; surrounding controls remain quiet.
- Desktop is one horizontal tape; mobile is a vertical strip without horizontal
  page scrolling. Loading, available, no-activity, suppressed, unconfigured,
  partial, stale, error/retry, permission, focus, reduced-motion, console, and
  overflow states must be explicit.

## Data and API

- Add closed response DTOs for adoption, runtime, cost, comparison direction,
  optional action, limitations, and read-only mode.
- Keep `organization_ref` mutually exclusive with program/course selection.
- Reuse the B07B organization-ref endpoint; no new selection endpoint.
- Execute two existing tool definitions in one workflow and record two bounded,
  content-free tool events.
- Recompute on projection and abstain when current source data or configured
  rates no longer match the stored digest.

## Security and failure behavior

- Execution and projection repeat active administrator membership and signed
  reference checks.
- SQL source failures are isolated. One unavailable projection preserves the
  other segment and produces a partial tape without exception text.
- Tool events contain names, status, latency, and bounded failure class only.
- Response and frontend bundles contain no environment rates, provider/model
  aliases, user IDs, course IDs, workflow breakdowns, or hidden low counts.

## Acceptance criteria

- [x] Only an active administrator can execute the signed organization workflow;
  wrong user, role, organization, and changed authorization fail closed.
- [x] Nonzero adoption suppression is indivisible at a five-user threshold in
  both current and comparison windows, and admin analytics runs are excluded.
- [x] Runtime and cost use only content-free organization events; missing rates
  never fabricate a price or operational action.
- [x] The response has exactly three segments, bounded facts, explicit windows,
  limitations, at most one real handoff, and no sensitive identifiers.
- [x] Changed events or rates make a completed tape abstain; isolated source
  failure preserves the other current projection.
- [x] Desktop/mobile state, focus, keyboard, handoff, reduced-motion, console,
  and overflow checks pass.
- [x] Batch-quality, product-UX, and agent-safety reviews have no open P0/P1.

## Test plan

- Unit/API: threshold edges (0/4/5 users), independent previous-window
  suppression, organization isolation, admin-run exclusion, terminal-state
  counts, p95, runtime thresholds, token totals, configured/unconfigured rates,
  stable/stale digest, partial source, idempotency, tool events, and no writes.
- Permission: every non-admin role, wrong user/org, inactive membership, and
  compatibility bypass.
- Browser: available tape, suppressed adoption, unconfigured cost, runtime
  attention/handoff, partial/error/retry, stale rerun, focus, reduced motion,
  desktop/mobile, overflow, and clean console.
- Regression: full pytest, frontend lint/build, full Canvas simulator,
  repo-wide pre-commit, and `git diff --check`.

## Batch review

- Initial reviews found three P1 blockers: administrator actors could contribute
  to the five-user adoption threshold through a non-admin workflow; small exact
  rate changes could leave the rounded public cost and result digest unchanged;
  and no-activity mobile E2E states inherited desktop activity from a shared
  database.
- Adoption now uses an explicit non-administrator role allow-list. The analytics
  digest includes exact normalized server rates read once for both calculation
  and digest, without exposing them. No-activity, retry, and stale browser
  scenarios now use one deterministic response fixture.
- One targeted recheck from each batch-quality, product-UX, and agent-safety
  reviewer passed with no remaining P0/P1.
- Final gate on 2026-08-03: 426 backend tests, frontend lint and production
  build, 54/54 desktop/mobile Canvas simulator tests, repo-wide pre-commit, and
  `git diff --check` passed. Desktop attention and mobile no-activity screenshots
  were inspected for focus, readability, and overflow.
- Deferred P2: classify unavailable SQL projections in tool events rather than
  recording them as succeeded; add explicit cross-organization, mid-run
  revocation, and partial-event-status regressions; load-test aggregate and p95
  projection timeouts on approved PostgreSQL; simplify runtime/p95/token language
  and raise the smallest evidence copy to 14 px before a broad nontechnical pilot.
