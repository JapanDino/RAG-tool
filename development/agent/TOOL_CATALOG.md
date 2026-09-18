# Agent tool catalog

Catalog version: `agent-tools.v1`

Status: implemented as an immutable declarative registry in B03

B03 records closed field sets, size limits, evidence boundaries, failure maps,
audit descriptors, and exact implementation targets, but does not execute a
tool. Before the first B04 adapter call, these declarative schemas must be bound
to strict typed runtime validation for every argument and result field.

## Registry rules

- Tools are server-registered and deny-by-default.
- Trusted organization, course, user, role, session, and policy are injected as
  `ToolContext`; they are not part of model/user arguments.
- Every call rechecks current authorization and resource visibility.
- Arguments and results use closed schemas with unknown-field rejection.
- Every tool declares role allow-list, timeout, output bound, evidence contract,
  failure mapping, and content-safe audit event.
- Tools cannot call a shell, execute code/SQL, fetch arbitrary URLs, select a
  provider/model, or receive raw credentials.
- Existing domain services remain authoritative; adapters do not duplicate
  retrieval, policy, authorization, audit, or Canvas logic.
- Model-callable tools are read-only or create non-consequential drafts. History
  deletion, review decisions, approvals, and Canvas writes are human actions
  outside this registry.

Machine-facing allow-lists use canonical runtime roles: `student`, `instructor`,
`methodologist`, `program_designer`, and `administrator`. "Learner" remains UI
language only.

Implementation labels:

- `existing`: callable service boundary already exists;
- `adapter`: behavior exists but needs a dedicated application-service adapter
  instead of invoking a FastAPI router from a tool;
- `planned`: named missing service owned by a future batch.

## Learner tools

| Tool | Workflow use | Roles | Implementation | Evidence/output boundary |
| --- | --- | --- | --- | --- |
| `get_current_course_map` | Locate current module/material | student | existing: `backend/app/services/course_map.py::build_course_map` | Published/available exact-course topology only |
| `retrieve_published_course_evidence` | Ground learner response | student | existing: `backend/app/services/course_qa.py::retrieve_student_tutor_context` | Student-visible non-assessment retrieval hits |
| `explain_with_citations` | Explain supported material | student | existing: `backend/app/services/course_qa.py::answer_course_question` | Validated citations or abstention |
| `give_assessment_safe_hint` | Help without solution delivery | student | existing: `backend/app/services/course_qa.py::classify_student_tutor_request` and `backend/app/services/course_qa.py::answer_course_question` | Guidance mode; expected answers excluded |
| `create_self_check` | Generate bounded formative check | student | planned B04: `LearnerSelfCheckService` using retrieved evidence | Question and rubric-free feedback; no graded answer |
| `open_authoritative_source` | Return to exact Canvas/external source | student | planned B04: `SafeSourceDestinationService` issues opaque refs from validated `destination_url` output of `backend/app/services/course_map.py::build_course_map` | Validated redirect/projection; no backend fetch |

## Instructor tools

| Tool | Workflow use | Roles | Implementation | Evidence/output boundary |
| --- | --- | --- | --- | --- |
| `get_teacher_course_summary` | Open exact course priorities | instructor | existing: `backend/app/services/teacher_workspace.py::build_teacher_workspace` | Exact-course evidence and aggregate tutor signals |
| `run_or_open_course_audit` | Start/open bounded audit | instructor | adapter B05 over `backend/app/services/course_audit.py::CourseAuditService` and existing audit lifecycle | Run status and evidence-backed results |
| `inspect_finding_evidence` | Understand one finding | instructor | planned B05: `FindingEvidenceProjectionService` extracted from `backend/app/routers/audits.py::list_findings` and `backend/app/routers/audits.py::finding_history` | Exact-course finding, evidence, confidence, history |
| `inspect_aggregate_question_gaps` | Find repeated unsupported topics | instructor | planned B06: `LearningGapAggregationService` | Minimum-cohort aggregate; no transcript/identity |
| `draft_course_improvement` | Draft cited remediation | instructor | existing: `backend/app/services/course_copilot.py::generate_copilot_suggestion` | Editable draft, citations, confidence, limitations |
| `preview_canvas_change_set` | Inspect proposed Canvas operations | instructor | existing: `backend/app/services/canvas_change_set.py::build_canvas_change_set` | Read-only exact-target preview |

## Program tools

| Tool | Workflow use | Roles | Implementation | Evidence/output boundary |
| --- | --- | --- | --- | --- |
| `get_program_competency_map` | Inspect course/competency coverage | methodologist, program_designer, administrator | adapter: `backend/app/services/program_agent.py::current_program_route_brief` over the bounded deterministic audit | Authorized aggregate map counts and current saved evidence; at most three findings |
| `inspect_program_gap` | Inspect coverage/duplication candidate | methodologist, program_designer, administrator | B07D adapter: `backend/app/services/program_agent.py::current_program_evidence_route` over the deterministic audit | At most one evidence-backed candidate with four anchors, uncertainty, review state, and truncation; not an automatic verdict |
| `inspect_prerequisite_path` | Inspect declared sequence | methodologist, program_designer, administrator | B07D adapter: `backend/app/services/program_agent.py::current_program_evidence_route` over the explicit prerequisite projection | At most one explicitly saved relation with current evidence; never an inferred relation or learner-readiness claim |
| `draft_program_review_note` | Prepare non-consequential review note | program_designer, administrator | B07F adapter: `backend/app/services/program_agent.py::current_program_review_draft` | One editable draft for the current bounded gap candidate, signed source fingerprint, current saved human decision; no map or Canvas mutation |

## Administrator tools

| Tool | Workflow use | Roles | Implementation | Evidence/output boundary |
| --- | --- | --- | --- | --- |
| `get_aggregate_adoption_health` | Inspect use without surveillance | administrator | B07C adapter `backend/app/services/admin_agent.py::current_admin_adoption_segment` | 28-day organization total at a five-user threshold; no role/workflow/course breakdown or low counts |
| `get_agent_latency_cost_health` | Operate model usage | administrator | B07C adapter `backend/app/services/admin_agent.py::current_admin_runtime_segments` | 24-hour content-free calls, p95, fallback/error, tokens, and cost only with configured flat rates |
| `get_integration_readiness` | Choose the next operational Canvas/AI check | administrator | B07B adapter `backend/app/services/admin_agent.py::current_admin_operations_brief` over LTI configuration, bounded pilot health, model-runtime readiness, and effective tutor-data policy | Four content-free stations and at most three ordered actions; no live probe or write |
| `get_retention_and_policy_status` | Inspect effective data policy | administrator | B07E adapter `backend/app/services/admin_agent.py::current_admin_policy_status` over `backend/app/services/tutor_data.py::get_effective_tutor_data_policy` and the safe deletion-receipt projection | Effective retention, 30-day agent-metadata cap, two policy-version rows, and at most one content-free organization-wide cleanup receipt; no person/course association or purge write |

## Human-confirmed actions outside the model registry

| Action | Actor | Existing/planned implementation | Mandatory boundary |
| --- | --- | --- | --- |
| `delete_own_conversation_history` | student | adapter B04 extending `backend/app/services/tutor_data.py::delete_owned_tutor_history` to agent-linked records | Direct endpoint, explicit confirmation, CSRF, current owner/course recheck, content-safe receipt |
| `review_improvement_draft` | instructor | adapter B05 over `backend/app/routers/copilot.py::review_suggestion`, extracted into an application service | Direct endpoint, server-issued artifact, expected version, exact target, CSRF, current authorization, audit event |
| `apply_canvas_change` | instructor | planned M06 only | Visible diff, exact target, version recheck, unpublished default, explicit confirmation, durable audit, rollback |

These names must not be exposed to the model as callable tools. The assistant may
render a user action leading to the direct endpoint after presenting the exact
scope and consequences.

## Explicitly rejected generic tools

The registry must never contain:

- `run_sql`, `database_query`, or arbitrary ORM access;
- `run_shell`, `execute_code`, or file-system access;
- `http_request`, `fetch_url`, browser control, or unrestricted search;
- `canvas_api_request` with arbitrary method/path/body;
- `send_message`, grading, roster, submission, or gradebook tools in the first
  pilot;
- caller-controlled prompt, provider, model, embedding, or system-policy tools;
- generic mutation tools that bypass review, versioning, and audit.

## Required matrix before registration

For every tool implementation, the active spec must supply:

| Check | Required evidence |
| --- | --- |
| Allowed role | Positive service/API test |
| Every other role | Non-disclosing deny test |
| Wrong organization/course/user | Isolation tests |
| Expired/revoked session | Execution-time deny test |
| Deleted/hidden/changed resource | Fail-closed or bounded refresh test |
| Unknown argument/output field | Schema rejection test |
| Timeout/budget/provider failure | Bounded recovery test |
| Prompt/tool-output injection | No tool/context escalation test |
| Audit event | Content-safe event assertion |
| Output/evidence bound | Size and citation-membership tests |
