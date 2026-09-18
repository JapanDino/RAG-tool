# B07D Program evidence routes

Status: done

## User outcome

A methodologist, program designer, or administrator selects one saved program
and asks one of two concrete questions: which declared coverage gap should be
reviewed first, or which explicitly saved prerequisite path needs evidence or
order review first. The assistant returns one bounded, read-only evidence route
and opens the corresponding existing review surface.

## Users and permissions

- Methodologist, program designer, administrator: run either route for one
  explicitly selected authorized program and open existing evidence.
- Instructor, student, anonymous, inactive, wrong-organization, wrong-user, and
  stale-program contexts receive a non-disclosing denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B07.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- Existing deterministic program audit and explicit prerequisite projection.
- `development/design/EXPERIENCE.md` and `DESIGN_SYSTEM.md` Workshop Route.

## Scope

- Make `program.inspect_gap.v1` and `program.inspect_prerequisite.v1`
  executable through the existing signed program reference and agent state
  machine.
- Gap routing considers current `coverage_gap`, `assessment_gap`,
  `evidence_gap`, and `duplication_check` audit findings; sequence-only findings
  remain outside this route.
- Prerequisite routing considers only explicitly saved prerequisite relations
  and their current saved-map evidence; it never infers a relation.
- Return at most one candidate with at most four bounded evidence anchors,
  explicit confidence/review/evidence state, truncation, limitations, and one
  exact handoff.
- Add one selectable program-review fork to the current program workspace.

## Non-goals

- No program-review note, generated recommendation, score, ranking, comparison,
  learner activity, expected answer, transcript, prompt, or person-level data.
- No new audit or prerequisite write, no Canvas/model/provider call, and no
  program or Canvas mutation.
- No real school Canvas or agent-host deployment and no research claim.

## User flow

1. The user opens an authorized saved program.
2. They select `Пробелы` or `Предпосылки` in the review fork.
3. They choose `Проверить выбранный вопрос`.
4. The agent rechecks the signed program, role, organization, user, and saved
   version and executes exactly one bounded tool.
5. One candidate or an honest empty/partial state appears. A single action opens
   the existing audit or prerequisite surface without changing it.

## UX contract

- Single job: choose one methodological question and reach its evidence.
- Signature element: a route switch with one source rail branching into the two
  actual review paths. The selected rail is cobalt; mint, yellow, apricot, and
  risk colors encode evidence/review states with text labels.
- Desktop uses a compact horizontal fork beside one result sheet. Mobile stacks
  the rails and result vertically with no page overflow.
- Exact primary action: `Проверить выбранный вопрос`; result action:
  `Открыть доказательства пробела` or `Открыть линии предпосылок`.
- Idle, loading, candidate, clear, empty, partial/truncated, stale, permission,
  failure/retry, program-switch, keyboard, focus, and reduced-motion states are
  explicit. One primary action exists per state.

## Data and API

- Add closed response DTOs for route kind/state, one optional candidate, bounded
  evidence anchors, action target, limitations, and read-only mode.
- Reuse `program_ref`, `AgentRun`, content-safe tool events, and result digest;
  no migration or response snapshot.
- Projection recomputes the exact bounded source and abstains after current
  audit, relation, evidence, or program-version changes.
- Update the two registry definitions to program-agent adapter boundaries with
  the exact closed output contract.

## Security and privacy

- Execution and projection repeat exact organization, user, role, program,
  active-membership, and signed-version checks.
- Imported evidence excerpts and saved rationale are untrusted display data,
  never instructions. No model is invoked.
- Tool choice is fixed by the routed workflow; user content cannot switch tools
  or trusted context.
- Evidence is bounded and belongs to the selected program and its authorized
  organization. Tool events contain only content-free execution metadata.

## Acceptance criteria

- [x] All three program roles can execute both signed read-only routes; all
  wrong or changed contexts fail closed.
- [x] Gap output selects only an authoritative allowed-kind finding, exposes its
  evidence/uncertainty, and never turns absence into a quality verdict.
- [x] Prerequisite output uses only an explicit relation, distinguishes missing
  evidence/order review/declared order, and never infers learner readiness.
- [x] Each response contains at most one candidate, four evidence anchors, one
  exact handoff, explicit limitations/truncation, and no sensitive content.
- [x] Changed audit, relation, evidence, or program version makes a completed
  route abstain; source failure is non-disclosing and retryable.
- [x] Desktop/mobile states, program switching, focus, keyboard, reduced motion,
  console, and overflow checks pass.
- [x] Batch-quality, product-UX, and agent-safety reviews have no open P0/P1.

## Test plan

- Unit/service: allowed finding kinds and priority, no-findings, no-relations,
  all prerequisite structural states, truncation, evidence bounds, stable/stale
  digest, and no writes.
- API/permission: three allowed roles, instructor/student, wrong org/user,
  inactive membership, stale reference, idempotency, and exact tool events.
- Browser: both branches, candidate/clear/empty/partial, error/retry, stale,
  handoff, program switch, focus, keyboard, reduced motion, desktop/mobile,
  clean console, and overflow.
- Regression: full pytest, frontend lint/build, full Canvas simulator,
  repo-wide pre-commit, and `git diff --check`.

## Batch review

- General quality, product UX/accessibility, and agent-safety reviewers each
  completed an independent review and targeted recheck with no open P0/P1.
- Review fixes added a canonical bounded-source fingerprint, terminal
  permission handling, one primary action per UI state, truthful
  `run.tool_running` events, and sticky-header-safe focus reveal.
- Final gates: `443 passed` backend tests; frontend lint and production build;
  `72 passed` desktop/mobile Canvas simulator tests; repo-wide pre-commit; and
  `git diff --check`.
- Deferred P2: replace the prerequisite route's full program-map projection
  with a dedicated bounded query, and return a partial state before selecting a
  candidate if legacy/imported relations exceed the supported limit.
