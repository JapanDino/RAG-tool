# B00 agent contract freeze

Status: done

## User outcome

The next implementation agent can build the Canvas AI agent against one
unambiguous, versioned, role-safe contract while reusing the current tutor,
course-audit, remediation, program, identity, and Canvas services.

## Users and permissions

- Implementation agent: may change project documentation only in this batch.
- Reviewer agents: read-only and limited to the intended documentation diff.
- Product users: no behavior, data, permissions, or interface changes.
- No actor receives new Canvas, model, database, or deployment access.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md`
- `development/PRODUCT.md`
- `development/ROADMAP.md`
- `development/ARCHITECTURE.md`
- `development/security/SECURITY_BASELINE.md`
- `development/integrations/CANVAS.md`
- current backend service, router, schema, model, and test names.

## Scope

- Move the completed local Canvas companion spec to `done/`.
- Create a separate queued clean self-hosted Canvas verification spec.
- Record accepted ADRs for bounded workflows, execution-time role/tool policy,
  and the organization agent-host model boundary.
- Define versioned agent message/run/evidence/error/event contracts.
- Map every initial product tool to an existing implementation or one explicit
  planned missing service.
- Update canonical development navigation and architecture references.

## Non-goals

- Implementing ModelGateway, AgentGateway, tools, migrations, endpoints, UI, or
  agent-host connectivity.
- Starting Docker or a Canvas deployment.
- Changing prompts, retrieval, model behavior, authorization, or user data.
- Committing, publishing, deploying, or mutating Canvas.

## User flow

1. Read the active spec and frozen agent contracts.
2. Select one workflow and its exact role/tool mapping.
3. Trace trusted context, evidence, errors, events, and missing implementation.
4. Create the next implementation spec without inventing a parallel contract.

## UX contract

No user-facing UI changes. Existing learner and instructor Canvas screens are
captured only as visual baselines for future comparison.

## Data and API

- Documentation-only schemas describe version `agent.v1`.
- Trusted organization, course, user, role, and product-session context is never
  accepted from message input.
- No migration or runtime endpoint is added in this batch.

## Security and privacy

- Models and imported content remain untrusted.
- No unrestricted database, shell, network, URL-fetch, or Canvas tool exists.
- Every future tool requires execution-time authorization and bounded output.
- Contracts contain no secrets, user data, school content, or raw transcripts.

## Acceptance criteria

- [x] Completed local companion and future clean-Canvas evidence are separate
  specs with truthful statuses.
- [x] Three accepted ADRs define the agent, role/tool, and model-host boundaries.
- [x] `agent.v1` request, run, evidence, error, and event schemas are explicit.
- [x] Every initial tool maps to an existing implementation or one named missing
  service; duplicates and unrestricted tools are rejected.
- [x] Organization, course, user, and role cannot be selected by message input.
- [x] Architecture, roadmap, plan, development index, and reviewer routing agree.
- [x] Documentation checks and batch-quality/agent-safety reviews have no open
  P0/P1 findings.

## Test plan

- Static trace: every tool row points to a real file/function or `planned` owner.
- Contract review: positive and negative context/error/event examples.
- Repository: targeted pre-commit and `git diff --check`.
- Visual baseline: existing signed learner and instructor routes at desktop.
- Batch review: batch-quality and agent-safety reviewers in parallel.

## Batch review

Completed on 2026-08-02. The local Canvas companion is now a truthful completed
spec, while clean official self-hosted Canvas verification is queued as a
separate environment-dependent slice. ADR-0001 through ADR-0003 freeze bounded
workflows, execution-time authorization, and the organization model-host
boundary. `agent.v1` freezes cookie/CSRF authentication, current-turn-only model
memory, exact role/course scope, evidence, errors, no-store events, retention,
and human-confirmed consequential actions. `agent-tools.v1` maps every initial
tool to an exact existing symbol or named future adapter/service and rejects
generic SQL, shell, network, URL-fetch, and Canvas tools.

Initial reviews found four P1 contract defects: missing cookie CSRF, `learner`
instead of canonical runtime `student`, model-callable deletion/review actions,
and unspecified conversation memory/retention/deletion. All four were fixed.
Targeted batch-quality and agent-safety rechecks passed with no remaining P0/P1;
the mapping-precision P2 notes were also resolved.

Static tool-target tracing, targeted pre-commit, and `git diff --check` passed.
Fresh signed desktop browser baselines passed separately for learner (1/1) and
instructor (1/1); screenshots are stored under
`output/playwright/b00-baseline/`. An attempted full browser matrix exceeded the
five-minute command limit after producing the first learner artifacts, so it is
not claimed as a new full-suite result; the previous completed 12-test matrix
remains the latest full simulator evidence. No product code, production data,
school Canvas state, deployment, commit, or publication changed in B00.
