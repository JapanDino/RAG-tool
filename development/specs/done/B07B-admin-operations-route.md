# B07B Administrator operations route

Status: done

## User outcome

An organization administrator opens the existing Canvas connection workspace
and asks the assistant what must be checked next. The assistant returns one
bounded, read-only operations route built from current integration, launch,
model-runtime, and retention-policy signals, with one primary next action and
direct handoffs to the existing operational surfaces.

## Users and permissions

- Administrator: request the route for one explicitly selected organization and
  open the relevant existing settings or evidence section.
- Student, instructor, methodologist, program designer, anonymous, inactive,
  wrong-organization, and compatibility-bypass contexts receive a
  non-disclosing denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B07.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- Existing LTI readiness, production registration, seven-day pilot health,
  model-runtime readiness, and tutor-data policy services.
- Administrator experience and Workshop Route rules in `development/design/`.
- This slice stays offline-capable. A later approved self-hosted Canvas Letovo
  gate must validate the same organization/account entry and real host behavior.

## Scope

- Issue a signed, user/role/organization-bound administrator context reference.
- Execute the existing `admin.integration_readiness.v1` workflow through the
  agent state machine, broadening its implemented adapter only to the four
  already-approved operational projections.
- Adapt existing projections without making network, model, Canvas, or policy
  writes and return at most four stations plus three ordered next steps.
- Embed the route in the existing Canvas connection workspace with direct
  handoffs to the relevant settings sections.

## Non-goals

- No adoption analytics, staff or student ranking, conversation feeds,
  transcript access, cost billing, provider secrets, production probe, Canvas
  write, policy write, or automatic registration change.
- No new infrastructure health collector, real Canvas deployment, or research
  benchmark in this slice.
- No claim that a configured or locally stable signal proves school production
  readiness.

## User flow

1. The administrator opens the selected organization connection workspace.
2. The page obtains a signed organization reference and the administrator
   chooses `Собрать маршрут действий`.
3. The assistant rechecks organization membership and reads four bounded
   current projections.
4. A dispatch route names one next action, explains its evidence window and
   limits, and moves focus to the exact existing section when opened.

## UX contract

- Single job: decide what the administrator should verify next.
- Continue Workshop Route; do not introduce chat, scores, opaque percentages,
  or another general-purpose dashboard.
- Signature element: a compact `dispatch route` where four operational stations
  converge on one apricot maintenance tag marked `Сначала`.
- Palette and typography reuse Workshop ink `#15315F`, grid paper `#F8FBFF`,
  route cobalt `#2457D6`, evidence mint `#83D8C7`, marker apricot `#FF9B73`,
  note yellow `#FFD95A`, and the local Segoe/Cascadia stacks.
- Desktop uses a horizontal four-station route; mobile becomes a vertical track
  without horizontal page scrolling. Only the next action gets expressive
  emphasis; other surfaces remain quiet.
- Idle, loading, result, no-activity, stale, error/retry, permission, and partial
  signal states state what was preserved. Focus moves to the result or alert,
  visible focus and reduced motion are required.

## Data and API

- Extend `AgentSelectionIn` with one signed `organization_ref`, mutually
  exclusive with course/program selections.
- Add a no-store endpoint that returns the selected authorized administrator
  organization and its signed reference.
- Add closed DTOs for station state, bounded aggregate evidence, priorities,
  limitations, and read-only result projection.
- Reuse `AgentRun.result_digest`; persist no response snapshot or raw operations
  payload. Recompute the current bounded result on projection and abstain when
  its digest changes.
- Update the typed registry entry to point at the implemented adapter while
  keeping more ambitious adoption/cost services explicitly planned.

## Security and privacy

- The organization reference is HMAC-bound to organization, user, role, and
  contract version. Execution and projection repeat active membership checks.
- LTI configuration is reduced to readiness state and blocker/warning counts;
  URLs, key IDs, client IDs, deployment IDs, and hostnames never enter the agent
  output or tool event.
- Launch and model evidence remains bounded aggregate data. No identities,
  course titles, prompts, responses, grades, submissions, or transcripts appear.
- Retention exposes policy days/version and boolean safeguards only. This tool
  cannot update or purge data.
- Existing saved/provider output is not interpreted as an instruction. The
  slice is deterministic and model-free; tool events remain content-free.

## Acceptance criteria

- [x] Only an active administrator can obtain and execute the signed organization
  route; wrong user, role, organization, and changed authorization fail closed.
- [x] The result contains exactly four bounded stations, at most three ordered
  next steps, evidence windows, limitations, and no sensitive identifiers.
- [x] Configuration, pilot, model, and retention states come from their existing
  authoritative services and make no writes or live provider/Canvas probes.
- [x] A changed underlying signal makes a completed route abstain instead of
  showing stale operational advice.
- [x] Desktop/mobile idle, loading, result, partial/error, retry, focus, handoff,
  reduced-motion, console, and overflow checks pass.
- [x] Batch-quality, product-UX, and agent-safety reviews have no open P0/P1.

## Test plan

- Unit: organization reference signing/resolution, state ordering, redaction,
  partial-source handling, stable digest, and stale projection.
- API: administrator success, multi-organization selection, wrong role/user/org,
  inactive membership, idempotency, no-store, bounded tool events, and no writes.
- Browser: build route, inspect primary action, hand off and focus existing
  section; loading, no-activity, error/retry, changed signal, desktop/mobile,
  overflow, reduced motion, and clean console.
- Regression: full pytest, frontend lint/build, full Canvas simulator,
  repo-wide pre-commit, and `git diff --check`.

## Batch review

- Initial batch-quality and product-UX reviews found two P1 issues: one failed
  authoritative projection could abort the entire route, and the retention
  action did not open a truthful operational surface. The UI also gave the
  rebuild action the same visual weight as the recommended next step.
- Each database-backed projection now runs in an isolated nested transaction.
  A SQLAlchemy source failure produces one `unavailable` station and a
  `partial` route while preserving the remaining current evidence. The
  retention action now opens and focuses a bounded read-only policy detail,
  and the rebuild action is visually secondary.
- The single targeted quality and product-UX recheck closed both P1 findings
  and reported no P0/P1 regressions. Agent-safety review reported no P0/P1.
- Final evidence: 418 backend tests passed; frontend lint and production build
  passed; all 8 B07B desktop/mobile scenarios passed. The full 42-scenario
  Canvas-simulator run had one transient focus failure in a pre-existing
  instructor scenario (41 passed); its isolated unchanged scenario passed on
  immediate recheck. Repo-wide pre-commit and `git diff --check` passed.
- Deferred P2 hardening includes PostgreSQL timeout/load rehearsal, additional
  tampered-reference and authorization-revocation regressions, clearer
  documentation of server-global versus organization-scoped signals, and
  reducing mobile summary density. These do not open the B07B safety boundary.
