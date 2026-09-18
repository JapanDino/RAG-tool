# Agent API contract

Contract version: `agent.v1`

Status: implemented through the B07B administrator operations slice

## Trust model

The existing secure product-session cookie or safe development-only identity
header identifies the principal. The server derives:

- `organization_id`;
- `course_id` when the launch is course-scoped;
- `user_id`;
- `role`;
- `registration_id` and `product_session_id` for LTI sessions;
- effective role/tool policy and retention versions.

None of these fields is accepted from a message body, model output, or tool
argument as authority. A bounded option endpoint may accept an organization or
program ID only to select among memberships already proven by the server; the
subsequent message carries a server-signed, user/role/resource-bound opaque ref.
Local development identities follow the same trusted context shape but remain
unavailable outside safe development mode.

Machine-facing runtime roles use the existing canonical values `student`,
`instructor`, `methodologist`, `program_designer`, and `administrator`.
"Learner" is user-facing product language only; workflow names may use the
`learner.*` namespace without changing the trusted role enum.

## Create or continue a run

    POST /agent/v1/messages
    Cookie: <existing HttpOnly product-session cookie>
    X-CSRF-Token: <token from GET /identity/session>
    Idempotency-Key: <opaque client-generated value>

Request:

```json
{
  "contract_version": "agent.v1",
  "message": "Объясни, как этот материал связан с заданием",
  "conversation_id": "optional opaque server-issued id",
  "client_request_id": "optional opaque UI correlation id",
  "selection": {
    "module_ref": "optional server-issued ref",
    "evidence_ref": "optional server-issued ref",
    "program_ref": "optional server-issued program ref",
    "organization_ref": "optional server-issued administrator ref"
  }
}
```

Constraints:

- `message`: 1-4000 Unicode characters after normalization;
- IDs and refs: opaque bounded strings previously issued in the same trusted
  course/session context;
- course, program, and organization selection scopes are mutually exclusive;
- unknown fields are rejected;
- `organization_id`, `course_id`, `user_id`, `role`, `tool`, `workflow`,
  `provider`, `model`, `system_prompt`, URLs, SQL, or code are not request fields.

Authentication and CSRF:

- browser product sessions use only the existing HttpOnly cookie; the raw
  product-session token is never copied into JavaScript or sent as a Bearer;
- every cookie-authenticated unsafe method requires the exact
  `X-CSRF-Token` returned by `GET /identity/session` for that session;
- missing, malformed, expired, or different-session CSRF tokens fail with the
  stable `CSRF_INVALID` error and no run is created;
- safe local development may use `X-Dev-User` only while both development auth
  and non-production environment gates are active; it is not a production
  credential or fallback;
- all run, event, response, review, and error projections send
  `Cache-Control: no-store`.

Accepted response (`202`):

```json
{
  "contract_version": "agent.v1",
  "run_id": "run_opaque",
  "conversation_id": "conversation_opaque",
  "status": "queued",
  "status_url": "/agent/v1/runs/run_opaque",
  "events_url": "/agent/v1/runs/run_opaque/events",
  "execute_url": "/agent/v1/runs/run_opaque/execute"
}
```

The same valid idempotency key and trusted principal returns the original run.
The key cannot replay a run for another principal, organization, course, or
expired product session. Reusing the same key with a different normalized
message or selection returns `CONFLICT`, including the concurrent-insert path.

## Advance a learner run

    POST /agent/v1/runs/{run_id}/execute
    Cookie: <existing HttpOnly product-session cookie>
    X-CSRF-Token: <token from GET /identity/session>

The request body is the exact original `AgentMessageIn`. Its server-computed
digest must match the accepted run. The B04 browser uses this bounded polling
seam to advance `queued` to `routing`, then to `generating` or `tool_running`,
and finally to a terminal state. Every advance and tool call revalidates the
current product session, organization, course, membership, role, selection,
tool contract, and relevant content visibility. The browser cannot select a
workflow, tool, model, provider, URL, or prompt.

## Run projection

    GET /agent/v1/runs/{run_id}

Only the exact run owner or an explicitly authorized content-safe operational
projection can read a run. An operational projection exposes aggregate health,
never this run response. Instructor and administrator roles do not inherit
access to learner conversations or individual run content.

```json
{
  "contract_version": "agent.v1",
  "run_id": "run_opaque",
  "conversation_id": "conversation_opaque",
  "workflow": "learner.explain_material.v1",
  "status": "completed",
  "user_state": {
    "label": "Ответ готов",
    "recovery_action": null
  },
  "response": {
    "mode": "answer",
    "content": "...",
    "confidence": {
      "band": "supported",
      "value": 0.81,
      "explanation": "Ответ подтверждён материалами курса"
    },
    "evidence": [
      {
        "evidence_ref": "ev_opaque",
        "kind": "course_excerpt",
        "title": "Материал курса",
        "excerpt": "Проверенный фрагмент",
        "module_title": "Раздел курса",
        "support": "direct",
        "visibility": "learner_published",
        "open_url": "/agent/v1/runs/run_opaque/evidence/ev_opaque/source",
        "source_label": "Открыть источник в Canvas",
        "provenance": "canvas"
      }
    ],
    "feedback_url": "/agent/v1/runs/run_opaque/feedback"
  },
  "review": null,
  "created_at": "2026-08-02T10:00:00Z",
  "updated_at": "2026-08-02T10:00:02Z"
}
```

Run states:

- `queued`;
- `routing`;
- `tool_running`;
- `generating`;
- `completed`;
- `abstained`;
- `failed`.

State transitions are server-owned. A successful HTTP response never implies a
supported educational answer; `abstained` is a valid terminal outcome.

Implemented learner, instructor, program-map, administrator-operations,
administrator-analytics, and administrator-policy workflows return a typed
terminal response or an explicit abstention. B07D also implements the two
program evidence routes; remaining planned role workflows may still project
`workflow_plan`.

For `program.inspect_gap.v1` and `program.inspect_prerequisite.v1`, the existing
`program_ref` remains bound to the exact organization, user, role, program, and
saved version. Each workflow executes exactly one deterministic read-only tool
and returns at most one candidate with four bounded evidence anchors, explicit
review/uncertainty and truncation, and one handoff to the existing audit or
prerequisite surface. Gap routing uses only current authoritative audit kinds;
prerequisite routing uses only explicitly saved relations. Projection recomputes
the bounded route and abstains when the audit, relation, evidence, or program
version changes. Neither route invokes a model, infers a relation or learner
readiness, or writes to the program or Canvas.

For `admin.integration_readiness.v1`, `organization_ref` is HMAC-bound to the
exact organization, administrator user, role, and contract version. The result
contains four aggregate stations (LTI configuration, seven-day launches,
30-minute model runtime, and retention policy), at most three ordered actions,
and no endpoint, key, client/deployment ID, provider secret, person, transcript,
or course content. Projection recomputes the current bounded result and hides a
completed route when its content-free digest no longer matches.

For `admin.analytics_health.v1`, the same signed `organization_ref` drives two
read-only tools and exactly three result segments. Adoption compares terminal
non-admin runs over 28 days with the preceding 28 days; each window independently
requires five distinct users before any count is exposed. Runtime compares
content-free organization model events over 24 hours with the preceding 24
hours. Cost is emitted only when both server-owned USD-per-million-token rates
are valid; missing rates return `unconfigured`, never zero or a fabricated
price. The result contains no person, role, workflow, course, model/provider,
prompt, response, transcript, or low-cohort identifier. Projection recomputes
events and rate configuration and abstains when the digest changes.

For `admin.policy_status.v1`, the same signed `organization_ref` executes only
`get_retention_and_policy_status`. The typed response contains the effective
organization tutor-data retention contract, the separate 30-day content-free
agent-run metadata cap, exactly two version rows, and at most one latest safe
cleanup receipt. Receipt lookup is limited to `automatic_retention` or
`admin_purge` events with no course or subject association; output includes only
aggregate deleted-record counts, receipt time, and policy version. A missing
receipt explicitly does not prove that cleanup never ran because an empty purge
creates no receipt. Policy and receipt reads fail independently into a partial
result. Execution performs no policy write or purge. Projection fingerprints the
effective policy plus the exact latest safe receipt identifier and content, so a
new otherwise-identical receipt or changed policy abstains instead of serving a
stale result.

B04 execution keeps the locked `AgentRun`, tool audits, answer creation, and
terminal state in one transaction. Tool events are flushed but never committed
between tools, so a concurrent final execute waits for the first executor and
then observes its terminal result. PostgreSQL statements and row-lock waits use
the remaining bounded timeout; learner retrieval uses deterministic local hash
embeddings with cooperative absolute-deadline checks and makes no provider or
network call.

## Evidence contract

```json
{
  "evidence_ref": "ev_opaque",
  "kind": "course_excerpt",
  "title": "Название материала",
  "excerpt": "Bounded authorized excerpt",
  "support": "direct",
  "visibility": "learner_published",
  "open_url": "/agent/v1/runs/run_opaque/evidence/ev_opaque/source",
  "source_label": "Открыть источник в Canvas",
  "provenance": "canvas"
}
```

Rules:

- evidence refs are opaque, course-scoped, role-filtered, and validated against
  the exact evidence offered to the workflow;
- raw Canvas URLs may be stored server-side but are returned only through a
  validated source projection or redirect contract;
- citation redirects repeat ownership, citation membership, quote, current
  publication/availability, module, and destination checks immediately before
  returning a no-store, no-referrer `303`;
- learner evidence never contains hidden content, expected answers, grades,
  submissions, roster data, reviewer identity, or credential material;
- model-created evidence refs are invalid.

## Event stream

    GET /agent/v1/runs/{run_id}/events

The transport may start as polling and later use SSE without changing event
semantics.

```json
{
  "contract_version": "agent.v1",
  "run_id": "run_opaque",
  "sequence": 3,
  "type": "run.generating",
  "occurred_at": "2026-08-02T10:00:01Z",
  "payload": {
    "status": "generating",
    "label": "Готовлю объяснение по материалам курса"
  }
}
```

Public event types:

- `run.accepted`;
- `run.routing`;
- `run.tool_running`;
- `run.generating`;
- `run.completed`;
- `run.abstained`;
- `run.failed`.

Events expose user-understandable progress, not chain-of-thought, hidden prompts,
raw tool arguments/results, credentials, or unrestricted model reasoning.
At most 100 public events and 8 KiB per event payload are retained per run. Event
replay expires 24 hours after a terminal state; longer-lived UI history is built
from the authorized domain records described below, not event payloads.

## Error contract

```json
{
  "contract_version": "agent.v1",
  "error": {
    "code": "SESSION_EXPIRED",
    "message": "Сессия курса завершилась. Откройте помощника снова из Canvas.",
    "retryable": false,
    "recovery_action": "relaunch_from_canvas",
    "request_id": "request_opaque"
  }
}
```

Stable public error codes:

- `INVALID_REQUEST` (`400`);
- `AUTHENTICATION_REQUIRED` (`401`);
- `SESSION_EXPIRED` (`401`);
- `CSRF_INVALID` (`403`);
- `ACCESS_DENIED` (`404`, non-disclosing);
- `RESOURCE_UNAVAILABLE` (`404`);
- `POLICY_BLOCKED` (`422`);
- `UNSUPPORTED_INTENT` (`422`);
- `CONFLICT` (`409`);
- `BUDGET_EXCEEDED` (`429` or terminal run failure);
- `PROVIDER_UNAVAILABLE` (`503`);
- `TEMPORARY_FAILURE` (`503`).

Errors never reveal another organization, course, user, role, registration,
tool, model origin, credential, hidden resource, or raw provider response.

## Conversation memory and retention

`agent.v1` does not provide hidden or autonomous long-term model memory.

- `conversation_id` is an opaque UI/history grouping over authorized domain
  records. In B02-B03, model context contains only the current message, explicit
  current selection, and evidence retrieved for the selected workflow.
- Prior messages are never automatically added to a prompt. Any future bounded
  multi-turn context requires a new contract version, maximum turn/character
  limits, same organization/course/user/runtime-role checks, and RAG/safety
  evaluation.
- A conversation is bound to the exact organization, course, user, and runtime
  role. It can be reopened after a fresh LTI launch only after those values and
  the current retention policy are revalidated. It cannot move between roles,
  courses, organizations, or users.
- Multiple tabs may reference the same conversation only for the same current
  principal. Idempotency prevents duplicate message runs; the server orders
  accepted runs and never trusts a client-supplied history transcript.
- Learner question/answer content continues to use the existing owned
  `CourseQuestionAnswer` persistence and effective organization tutor retention
  policy. Instructor/program drafts continue to use their existing reviewed
  domain entities. Generic `AgentRun`, step, event, and model-invocation records
  contain no raw message, response, prompt, retrieved excerpt, or transcript.
- Student-linked content-free agent metadata is retained for at most the lesser
  of 30 days and the effective tutor retention period. Public event replay has
  the shorter 24-hour limit above. Longer-term operational reporting uses
  minimum-cohort aggregates without user or transcript fields.
- The human-initiated owner deletion endpoint must delete owned questions,
  answers, feedback, conversation pointers, and any student-linked run/step
  references in one course-scoped service transaction. It leaves only a
  content-free deletion receipt. Already released minimum-cohort anonymous
  aggregates cannot be reidentified or reversed and must be disclosed as such.
- Research retention never inherits product defaults silently; it requires an
  approved protocol and separate consent/assent contract before collection.

## Review contract

Consequential instructor/program actions produce an `awaiting_review` run with
a server-issued review artifact. Review submission uses a separate versioned
human-action endpoint and requires current authorization, CSRF, exact target,
plus the expected artifact version. History deletion is also a separate
human-action endpoint with CSRF and explicit confirmation. Neither action is
registered as model-callable. The model cannot approve its own output or delete
history. Canvas mutation remains unavailable until M06 and requires its separate
exact-target/diff/version/audit contract.

## Negative examples

The following bodies are invalid and must not be silently ignored:

```json
{"contract_version":"agent.v1","message":"help","role":"instructor"}
```

```json
{"contract_version":"agent.v1","message":"help","course_id":42}
```

```json
{"contract_version":"agent.v1","message":"help","tool":"run_sql"}
```

```json
{"contract_version":"agent.v1","message":"help","model":"unapproved"}
```

Required CSRF negative tests cover a missing token, malformed token, token from
another session, expired session, and safe-method behavior. All unsafe failures
must prove that no run, review, deletion, or audit mutation occurred.
