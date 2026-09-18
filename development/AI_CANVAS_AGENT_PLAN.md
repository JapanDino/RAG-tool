# Canvas AI agent delivery plan

Status: planned

This document is the technical execution plan for turning the current course
intelligence platform into a role-aware AI agent delivered inside Canvas. It is
more detailed than `ROADMAP.md`; one batch at a time must still be expressed as
an active spec under `development/specs/active/`.

## Target outcome

A learner, instructor, program designer, methodologist, or administrator opens
one familiar assistant entry point from Canvas. The product derives the exact
organization, course, user, and role from a verified LTI launch, offers only the
tools allowed for that context, and returns evidence-backed results. It never
gives the model Canvas credentials or unrestricted database/network access.

The product is one assistant in the interface, but not one universal agent in
the trust boundary. Each role receives a separate policy, tool allow-list,
context projection, retention contract, and evaluation suite.

## How the existing product is reused

The original course-audit product remains the evidence and action engine:

- import, extraction, retrieval, course audit, findings, and evaluation;
- grounded student tutor with citations, assessment protection, and abstention;
- teacher remediation drafts and review history;
- program competencies, contributions, prerequisites, and aggregate views;
- identity, organization/course memberships, and LTI product sessions;
- the synthetic Canvas interaction and signed-launch test harness.

Canvas is the delivery and source adapter. The new agent layer coordinates the
existing bounded services. It must not replace them with free-form model tool
calls or duplicate their authorization logic.

## Target component boundaries

    Canvas course navigation placement
                  |
                  v
          verified LTI product session
                  |
                  v
             AgentGateway
        +---------+----------+
        |                    |
        v                    v
    RolePolicy          WorkflowRouter
        |                    |
        +---------+----------+
                  v
             ToolRegistry
        student | teacher | program | admin
                  |
        +---------+----------+
        |                    |
        v                    v
    EvidenceLayer        ModelGateway
        |                    |
        +---------+----------+
                  v
          validated response/event

### AgentGateway

- Accepts only an authenticated local development principal or verified LTI
  product session.
- Resolves organization, course, user, role, session expiry, and policy version
  before creating a run.
- Exposes one versioned message/run contract to the frontend.
- Does not accept organization, course, role, provider, or unrestricted tool
  names from user-controlled input.

### RolePolicy

- Returns an immutable allow-list of workflows and tools for the exact run.
- Rechecks membership and resource visibility at every tool execution.
- Keeps student, instructor, program, and administrator context projections
  separate.
- Requires an explicit human approval artifact for every consequential write.

### WorkflowRouter

- Uses a bounded intent schema, not an open-ended autonomous planner.
- Selects from known workflows such as explain material, create self-check,
  inspect a course finding, draft an improvement, or inspect a program gap.
- Rejects unsupported intents and asks one bounded clarification when required.
- Has maximum step, tool-call, latency, and token budgets.

### ToolRegistry

Each tool has a typed request/response schema, role allow-list, timeout, output
size limit, evidence contract, audit event, and negative permission tests.

Initial learner tools:

- `get_current_course_map`;
- `retrieve_published_course_evidence`;
- `explain_with_citations`;
- `give_assessment_safe_hint`;
- `create_self_check`;
- `open_authoritative_source`.

Initial instructor tools:

- `get_teacher_course_summary`;
- `run_or_open_course_audit`;
- `inspect_finding_evidence`;
- `inspect_aggregate_question_gaps`;
- `draft_course_improvement`;
- `preview_canvas_change_set`.

Human-confirmed application actions are not model-callable tools. History
deletion and draft review use separate direct endpoints with current
authorization, CSRF, exact target, expected version where applicable, explicit
confirmation, and a content-safe audit/deletion receipt. Canvas writes remain
disabled until M06.

Initial program tools:

- `get_program_competency_map`;
- `inspect_program_gap`;
- `inspect_prerequisite_path`;
- `draft_program_review_note`.

Initial administrator tools:

- `get_aggregate_adoption_health`;
- `get_agent_latency_cost_health`;
- `get_integration_readiness`;
- `get_retention_and_policy_status`.

Administrator tools must not expose tutor transcripts, individual student
rankings, or automatic teacher-performance judgments.

### ModelGateway

- Provides one OpenAI-compatible adapter for the organization agent host,
  including DeepSeek and Gemma deployments.
- Records provider, model, prompt/workflow version, latency, token counts,
  failure class, and fallback without recording credentials.
- Validates structured output before any downstream action.
- Supports task-specific routing and deterministic fallback.
- Keeps retrieval, policy, authorization, and citation membership outside the
  model.

### EvidenceLayer

- Converts authorized course objects into bounded evidence references.
- Treats imported text, Canvas HTML, links, and model output as untrusted.
- Validates every returned citation against the evidence offered to the model.
- Records why the agent answered, abstained, requested review, or rejected a
  tool call.

## Persistence additions

Prefer extending existing course-question, finding, suggestion, evaluation, and
product-session entities. Add generic agent persistence only where cross-role
run observability cannot be represented safely by existing tables.

Candidate additions:

- `AgentRun`: actor, organization, course, role, workflow version, status,
  policy version, timestamps, and content-free failure class;
- `AgentStep`: bounded workflow step, selected tool, result status, duration,
  and evidence IDs, without credentials or raw hidden content;
- `ModelInvocation`: provider/model/prompt version, latency, token counts,
  structured-validation result, and cost estimate;
- `LearningGapAggregate`: course/topic/time-window counts with minimum cohort
  thresholds and no student transcript;
- `TeacherIntervention`: aggregate gap, cited draft, reviewer decision, edit
  distance, and optional approved Canvas change-set link;
- `ExperimentAssignment`: protocol version and anonymous condition identifier
  for approved research only.

Every migration must have an idempotent clean-PostgreSQL rehearsal and a safe
existing-data path. Raw prompts and transcripts must not be copied into generic
operational events.

## Execution batches

Each batch is a two-to-five day vertical slice. Create exactly one active spec,
implement it, run focused checks, perform the listed independent reviews in
parallel, fix P0/P1, run one targeted recheck, move the spec to `done/`, and
update `STATUS.md` once.

Dependency order:

    B00 -> B02 -> B03 -> B04 -> B05 -> B06 -> B09 -> B10
      |             |             |                  ^
      |             +-----------> B07                |
      +-----------> B01 -----------------------------+
                    B02/B03 -> B08 ------------------+

B01 starts whenever the clean Canvas environment is available; it does not
block B02-B07 development against the signed simulator. B01 and B08 are hard
gates for a real hosted pilot and B10, not for local agent implementation.

### B00 — Reconcile the M05 gate and freeze contracts

Estimate: 1-2 focused days.

Outcome:

- Move the completed local companion work to `done/`.
- Create a separate queued spec for clean self-hosted Canvas verification so an
  unavailable Docker/Canvas environment does not keep a completed coding slice
  artificially active.
- Add ADRs for the bounded workflow agent, role/tool policy, and agent-host
  model boundary.
- Inventory existing tutor, audit, Copilot, program, identity, LTI, and Canvas
  services as candidate tools; explicitly reject duplicate implementations.
- Define versioned agent request, response, evidence, error, and event schemas.

Gate:

- Every initial tool maps to one existing service or one explicitly planned
  missing service.
- No tool accepts caller-selected organization, course, or role.
- Architecture and roadmap agree on milestone order.

Reviews: batch quality, agent safety.

### B01 — Clean self-hosted Canvas contract verification

Estimate: 3-6 focused days after Docker/host availability.

Outcome:

- Start a separate official open-source Canvas LMS deployment with synthetic
  users and courses only.
- Install the development LTI 1.3 course-navigation registration.
- Verify learner and instructor launches, iframe/cookie/session behavior,
  issuer/client/deployment/JWKS handling, exact course binding, logout/expiry,
  mobile width, and rollback.
- Exercise a read-only API token/OAuth path against the clean instance and
  preserve ordered module topology and source provenance.

Gate:

- The same exact-role flow tested by the simulator passes against real Canvas.
- Cross-role, cross-course, expired-session, malformed claim, blocked cookie,
  and unavailable-tool states fail closed.
- No school Canvas data, cookies, credentials, branding assets, or content are
  copied into the environment.

Reviews: Canvas integration, batch quality, product UX.

### B02 — ModelGateway and agent-run foundation

Estimate: 3-5 focused days.

Outcome:

- Implement the central OpenAI-compatible ModelGateway and configuration for
  the agent host.
- Add bounded `AgentRun` and `ModelInvocation` observability.
- Add provider timeout, retry, circuit-breaker, concurrency, token, and cost
  limits.
- Add schema validation and deterministic fallback.
- Expose a health/readiness projection without secrets.

Gate:

- DeepSeek/Gemma-compatible mocked contract tests pass without a real provider.
- Provider outage never bypasses policy or returns unvalidated output.
- Existing tutor and Copilot behavior remain backward compatible.

Reviews: batch quality, RAG evaluator, agent safety.

### B03 — RolePolicy, ToolRegistry, and bounded workflow routing

Estimate: 4-6 focused days.

Outcome:

- Implement typed tool definitions and per-role allow-lists.
- Reuse existing authorization services inside every tool adapter.
- Add deterministic workflow routing first; allow a model-selected workflow
  only through a closed enum and validated structured output.
- Add per-run step/tool/time budgets and content-safe audit events.
- Add prompt-injection and tool-output-injection defenses.

Gate:

- A compromised prompt cannot select an unlisted tool, change course/role, or
  pass arbitrary parameters to a database, network, shell, or Canvas client.
- Authorization is checked at execution time, not only at launch or planning.
- All role/tool pairs have explicit allow and deny tests.

Reviews: agent safety, batch quality, RAG evaluator.

### B04 — Learner agent inside the current Canvas course

Estimate: 4-6 focused days.

Outcome:

- Replace the fixed companion action handoff with the versioned learner-agent
  message/run contract while preserving the current course map.
- Support cited explanation, assessment-safe hint, self-check, abstention,
  source opening, feedback, and own-history deletion.
- Keep the exact launched course and selected module as server-owned context.
- Stream or progressively render bounded step status without exposing internal
  chain-of-thought.

Gate:

- A learner completes find material, ask for help, and self-check tasks without
  integration jargon or course reselection.
- Hidden/unpublished/assessment-answer/cross-course requests fail safely.
- Citation integrity, refusal, assessment guard, latency, mobile iframe,
  keyboard, loading, error, low-confidence, and recovery states pass.

Reviews: product UX, RAG evaluator, agent safety, batch quality.

### B05 — Instructor agent and reviewable course actions

Estimate: 5-8 focused days.

Outcome:

- Provide one instructor assistant entry point for course summary, audit,
  finding evidence, draft improvement, and change-set preview.
- Present every draft with evidence, confidence, limitations, and review status.
- Preserve editable drafts and explicit accept/reject decisions.
- Keep Canvas mutation disabled.

Gate:

- The instructor can move from a question to a cited draft without navigating
  an engineering dashboard.
- No model output becomes an accepted draft without explicit review.
- Learners cannot enumerate or execute instructor workflows.

Reviews: product UX, RAG evaluator, agent safety, batch quality.

### B06 — Closed student-to-teacher improvement loop

Estimate: 5-8 focused days.

Outcome:

- Aggregate repeated unsupported or low-helpfulness topics over a bounded time
  window with minimum cohort thresholds.
- Link an aggregate gap to authorized course evidence, not raw transcripts.
- Let the instructor inspect the signal and request a cited intervention draft.
- Record review decision, edit distance, time-to-decision, and later course
  version comparison.

Gate:

- One student cannot be reidentified from an aggregate or trigger a visible
  teacher signal alone.
- The signal is described as a course-improvement candidate, not a judgment
  about a student or teacher.
- End-to-end synthetic tests cover question -> aggregate -> draft -> review.

Reviews: agent safety, product UX, RAG evaluator, batch quality.

### B07 — Program and administration agent tools

Estimate: 4-7 focused days.

Outcome:

- Wrap existing program map, gap, prerequisite, portfolio, integration-health,
  retention, latency, and cost projections as bounded tools.
- Provide role-specific assistant surfaces for methodologists, program
  designers, and administrators.
- Keep people, transcripts, grades, and individual rankings out of aggregate
  administration responses.

Gate:

- Program conclusions expose evidence and uncertainty.
- Administrator responses are aggregate and operational.
- Every cross-course tool rechecks organization and program membership.

Reviews: product UX, agent safety, batch quality; RAG evaluator when generation
or retrieval changes.

### B08 — Agent-host deployment and operations

Estimate: 4-7 focused days after host access.

Outcome:

- Deploy backend/frontend/worker against the approved organization agent host.
- Route task classes to approved DeepSeek/Gemma models.
- Add health, latency, token/cost, fallback, error-rate, and saturation metrics.
- Add secret custody, rotation, network allow-lists, backups, retention jobs,
  incident rollback, and deployment canaries.

Gate:

- No provider or Canvas credential reaches prompts, logs, frontend bundles, or
  Markdown configuration.
- Provider outage has a bounded degraded experience.
- Synthetic public canaries verify login/LTI, one learner task, one instructor
  task, and permission denials after deployment.

Reviews: agent safety, Canvas integration, batch quality.

### B09 — Research benchmark and reproducible protocol

Estimate: 6-10 focused days for infrastructure; data collection is separate.

Outcome:

- Freeze the primary research question: whether a role-aware,
  evidence-constrained, uncertainty-aware LMS agent improves supported task
  completion and teacher course-improvement efficiency over a standard RAG
  assistant.
- Compare at least: Canvas/search baseline, standard course RAG, and the bounded
  role-aware agent.
- Create Russian/English course-level train/development/test splits with hidden,
  assessment, unsupported, prompt-injection, and cross-role cases.
- Record dataset hashes, model/prompt/workflow versions, retrieval configuration,
  latency, tokens, cost, and failures.
- Add an exportable, privacy-reviewed experiment report.

Primary metrics:

- supported-answer correctness and citation entailment;
- forbidden-content and cross-role leakage rate;
- selective accuracy, calibration error, abstention precision/recall;
- learner task completion and pre/post learning gain;
- instructor time-to-decision, acceptance rate, and edit distance;
- latency and cost per successful task.

Gate:

- Hypotheses, primary endpoints, exclusions, and analysis plan are frozen before
  pilot data is inspected.
- Tuning and final evaluation use different course splits.
- Synthetic regression results are not presented as classroom effectiveness.
- Any study involving students has institutional approval, consent/assent,
  data-minimization, opt-out, and retention rules before collection.

Reviews: research methodology, RAG evaluator, agent safety, batch quality.

### B10 — Approved pilot and Canvas write-back

Estimate: 5-10 focused engineering days plus external approval and pilot time.

Outcome:

- Run a small approved learner/instructor pilot on non-sensitive courses.
- Collect only protocol-approved outcomes and operational evidence.
- Implement M06 teacher-approved Canvas writes with visible diff, exact target,
  version recheck, unpublished draft default, one confirmation per operation,
  durable operation log, and recovery.

Gate:

- Product success thresholds and research analysis are reported separately.
- No autonomous grading, submission analysis, personnel judgment, or automatic
  publication is introduced.
- A rollback rehearsal and post-write Canvas verification pass.

Reviews: Canvas integration, agent safety, product UX, RAG evaluator, research
methodology, batch quality.

## Reviewer-agent routing

Reviewers are read-only and run only after the slice meets its acceptance
criteria and focused checks pass. Independent reviews should run in parallel.
The implementation agent fixes P0/P1 findings and requests one targeted recheck.

| Reviewer | Required batches | Contract |
| --- | --- | --- |
| Batch quality | Every batch | `development/agents/batch-quality-reviewer.md` |
| Product UX | B01, B04-B07, B10 | `development/agents/product-ux-reviewer.md` |
| RAG evaluator | B02-B06, B09-B10; B07 if model behavior changes | `development/agents/rag-evaluator.md` |
| Canvas integration | B01, B08, B10 | `development/agents/canvas-integration-reviewer.md` |
| Agent safety | B00, B02-B10 | `development/agents/agent-safety-reviewer.md` |
| Research methodology | B09-B10 | `development/agents/research-methodology-reviewer.md` |

No reviewer may edit, commit, push, deploy, mutate Canvas, broaden the active
spec, or mark `STATUS.md` complete.

## Verification matrix

Run focused checks during implementation and the complete relevant matrix at a
batch boundary.

Backend and data:

- unit tests for policy, schemas, workflow routing, tools, citations, budgets,
  provider fallbacks, and aggregation thresholds;
- API tests for every role, course, organization, expiry, revocation, malformed
  input, concurrency, and retry boundary;
- clean PostgreSQL migrations plus existing-data rehearsal;
- Redis/Celery retry, idempotency, and scheduled retention checks.

RAG and models:

- course-level held-out retrieval evaluation;
- citation membership and entailment;
- uncertainty calibration and selective answering;
- prompt/tool-output injection, unknown citations, empty context, provider
  timeout, invalid JSON, and budget exhaustion;
- DeepSeek/Gemma compatibility without tuning the final test split.

Canvas:

- simulator production-build E2E on desktop and 390 px;
- self-hosted Canvas LTI/OIDC/JWKS/iframe/cookie/role tests;
- read-only sync ordering, provenance, deleted/hidden/locked content, unsafe
  URLs, refresh failure, and rollback;
- real school integration only after explicit approval and credentials.

UX and accessibility:

- loading, empty, error, permission, low-confidence, abstention, partial-result,
  approval, and recovery states;
- keyboard, focus, accessible names, contrast, reduced motion, long Russian
  text, mobile iframe, and clean console/network output;
- task-based checks with role-appropriate vocabulary and no RAG/OAuth jargon in
  learner workflows.

Repository gates:

    python -m pytest -q
    pre-commit run --all-files
    cd frontend
    npm run lint
    npm run build

Relevant Playwright suites and `git diff --check` must also pass. Test output,
browser evidence, benchmark artifacts, and reviewer outcomes are recorded in the
completed spec, not duplicated as a chronological log across documents.

## Critical path and estimates

Engineering estimates assume the current repository baseline, focused AI-assisted
development, one implementation agent, batch-boundary parallel reviewers, and
prompt access to required infrastructure.

| Delivery point | Focused engineering time | External dependency |
| --- | ---: | --- |
| Agent foundation usable in simulator (B00, B02-B04) | 12-19 days | None beyond local services |
| Real self-hosted Canvas read-only agent (add B01) | 15-25 days | Docker/Canvas environment |
| Closed learner-teacher loop (add B05-B06) | 25-41 days | Teacher validation improves quality |
| Program/admin plus hosted pilot candidate (add B07-B08) | 33-55 days | Agent-host access and secret policy |
| Research-ready system (add B09) | 39-65 days | Labeled courses and ethics plan |
| Approved pilot/write-back (add B10) | 44-75 days | Canvas admin, accounts, approval, pilot time |

These are engineering days, not calendar promises. Access approvals, Canvas
operations, course labeling, teacher review, and student-study approval can be
the dominant calendar time.

## Product definition of done

The project satisfies the original assignment only when all of the following
are true:

- the assistant opens from a real Canvas course through verified LTI;
- the exact user, organization, course, and role are server-derived;
- learner and teacher tasks work through one understandable assistant entry;
- the agent uses typed, permission-checked tools rather than unrestricted model
  actions;
- answers and recommendations expose valid evidence, confidence, and review
  state;
- learner failures can become privacy-safe, teacher-reviewable improvement
  candidates;
- no consequential Canvas write occurs without explicit approval and audit;
- agent-host models have bounded latency, cost, fallback, and observability;
- desktop/mobile/accessibility and negative-permission E2E pass;
- real pilot metrics show learning or time-saving value beyond chat usage;
- research claims are supported by a frozen protocol and held-out evaluation.
