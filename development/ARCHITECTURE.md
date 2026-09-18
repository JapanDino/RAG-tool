# Architecture

## Current system

The repository currently contains:

- Next.js Pages Router frontend;
- FastAPI backend;
- PostgreSQL with pgvector;
- Redis and Celery;
- course import, extraction, alignment, audit, Q&A, and remediation services;
- OpenAI-compatible model access with deterministic fallbacks;
- read-only Canvas import and a reviewable Canvas change set;
- a verified local LTI 1.3 launch boundary with explicit identity/course bindings;
- immutable evaluation protocol snapshots.

Current course-domain code is concentrated in `backend/app/services/`,
`backend/app/routers/courses.py`, `backend/app/routers/audits.py`, and
`frontend/components/CourseAuditor.tsx`.

## Target boundaries

    UI shells
      student | teacher | curriculum | administration
                         |
                         v
                    AgentGateway
          trusted context | bounded workflow
                         |
                         v
    FastAPI application services
      identity | courses | tutor | audit | program intelligence
                         |
             +-----------+-----------+
             |                       |
             v                       v
        PolicyEngine             ModelGateway
             |                       |
             +-----------+-----------+
                         |
                         v
          course evidence and evaluation layer
                         |
              +----------+----------+
              |                     |
              v                     v
        LMSConnector           FileConnector

## Agent orchestration boundary

The Canvas assistant target is a bounded workflow agent, not a general
autonomous planner. The durable decisions are recorded in:

- `development/decisions/ADR-0001-bounded-role-aware-workflows.md`;
- `development/decisions/ADR-0002-execution-time-role-tool-policy.md`;
- `development/decisions/ADR-0003-agent-host-model-boundary.md`.

`AgentGateway` derives trusted organization, course, user, role, session, and
policy context from the authenticated principal. A closed `WorkflowRouter` may
select only versioned supported workflows. A deny-by-default `ToolRegistry`
injects trusted context separately from model/user arguments and rechecks
authorization at every execution. The versioned API and tool mappings are
defined in `development/agent/`.

The model may classify intent and produce validated structured content. It
cannot choose a provider/origin, invent tools, change trusted context, call a
database/shell/arbitrary network endpoint, approve its own output, or receive
Canvas/provider credentials. Existing tutor, audit, remediation, program, and
Canvas services remain authoritative tool implementations.

## Target domain additions

The identity boundary now includes:

- `Organization`;
- `User`;
- `OrganizationMembership`;
- `CourseMembership`;
- `MembershipAuditEvent`.

The LTI launch boundary now includes:

- `LtiRegistration` for one exact issuer, client, deployment, authorization
  endpoint, JWKS endpoint, tool launch URL, and organization;
- `LtiSubjectBinding` and `LtiContextBinding` for explicit platform-to-product
  identity and course mapping;
- `LtiLaunchAttempt` for short-lived one-use state and nonce digests;
- `LtiLaunchAuditEvent` for privacy-minimal accepted/rejected outcomes after a
  registration is known;
- `LtiProductSession` for a short-lived, revocable, course-scoped learner or
  instructor handoff after a verified launch;
- `LtiRegistrationEvent` for content-minimal administrator changes to a
  production registration.

An LTI message authenticates the platform assertion but does not by itself grant
product access. The resolved platform role must intersect an existing active
internal membership in the bound organization and course. Launch claims never
provision or mutate users, courses, or roles. A verified learner or instructor
may receive a short-lived product session for the exact bound course; unsupported
roles receive confirmation without a product session. Registration drafts stay
inactive until an administrator explicitly activates them after public-tool and
platform endpoint trust checks.

The public Canvas registration package contains an anonymous course-navigation
placement, no LTI Advantage scopes, and a public-only RSA JWKS. Draft creation
performs structural validation only and no DNS or network access; activation
applies exact host and resolved-address policy. Private signing material remains
outside this application.

Program intelligence now includes:

- `Program`;
- `ProgramCourse`;
- `Competency`;
- `CourseContribution`;
- `ProgramPrerequisiteRelation`;
- `ProgramChangeEvent`.

The following entities are still planned:

- `ProgramOutcome`;
- `ProgramAudit`.

Until a persisted `ProgramAudit` review workflow is justified, the first M04
audit slice is a bounded, read-only projection over explicit program courses,
competencies, contributions, and their evidence. It must not invent prerequisite
relations or store an automatic quality score.

Explicit prerequisite relations are a separate human-authored graph inside one
program. Writes use the program version, reject self-links and cycles, and store
content-free change events. Read projections compare the earliest saved
prerequisite assessment with the earliest saved target contribution. The result
describes only whether the current structure matches the declared order; it is
not learner readiness, progress gating, or an inferred pedagogical verdict.

## Required interfaces

### LMSConnector

- identify the LMS and course;
- import authorized course content;
- detect content changes;
- map LMS roles to internal memberships;
- prepare an approved change set;
- apply a change only through an explicit, audited workflow.

### ModelGateway

- route tasks to a configured OpenAI-compatible model;
- validate structured output;
- record provider, model, prompt version, latency, and failure class;
- enforce timeouts, token limits, and fallback behavior;
- expose no direct database or LMS credentials to the model.

### PolicyEngine

- resolve organization, course, role, and resource visibility;
- distinguish student tutoring from instructor assistance;
- restrict active assessment help;
- block hidden or unpublished content;
- require human approval for consequential actions.

## Frontend evolution

Keep the current Pages Router. Extract components incrementally into:

    frontend/components/ui/
    frontend/components/layout/
    frontend/components/student/
    frontend/components/teacher/
    frontend/components/curriculum/
    frontend/components/shared/
    frontend/lib/api/
    frontend/styles/tokens.css

Avoid a repository-wide frontend rewrite. Each active spec may extract only the
components needed for its user flow.

## Data and trust boundaries

- Imported course text is untrusted content, never system instruction.
- Model output is untrusted until schema and citation validation pass.
- Canvas and provider tokens are secrets and must not appear in logs or prompts.
- Student and teacher data stay within organization and course boundaries.
- Administrative analytics are aggregated unless a documented operational need
  and permission allow drill-down.
