# ADR-0002 — Execution-time role and tool policy

Status: accepted

Date: 2026-08-02

## Context

An LTI assertion proves a platform message, but product access also depends on
active internal organization/course memberships, exact subject/context
bindings, session state, resource visibility, and the requested operation. A
role check performed only at launch or planning time can become stale and is
insufficient against confused-deputy and cross-course attacks.

## Decision

Trusted agent context is derived only from the authenticated product session or
local development principal. Agent message bodies may not select organization,
course, user, role, registration, product session, model, provider, system
prompt, or tool name.

Every tool execution must:

1. Load the active run and trusted principal.
2. Revalidate session expiry/revocation and exact organization/course/user/role.
3. Resolve the tool from a deny-by-default versioned registry.
4. Recheck the tool's role and resource visibility with existing authorization
   services.
5. Validate a closed request schema and reject unknown fields.
6. Enforce timeout, call count, output size, evidence, and audit requirements.
7. Return a bounded result or a non-disclosing error.

Models receive no raw credentials and cannot call database, shell, unrestricted
network, arbitrary URL-fetch, or generic Canvas tools. Consequential writes
require a separate server-side approval artifact, version recheck, and audit
record outside the model.

## Alternatives considered

- Trust the role and course copied into the agent request: rejected because the
  browser and model are untrusted.
- Check permissions only when creating a conversation: rejected because
  sessions, memberships, policies, and course resources can change mid-run.
- Let tools perform ad hoc authorization independently: rejected because this
  produces inconsistent gaps and makes the role/tool matrix unauditable.

## Consequences

### Positive

- Exact course and role isolation survives stale plans and malicious prompts.
- Tool permissions can be enumerated and tested as a matrix.
- Revocation and policy changes take effect before the next action.

### Negative

- Every tool call has an additional authorization/database cost.
- Tool adapters must accept trusted context separately from model-controlled
  arguments.
- Long runs may terminate when a session or membership changes, requiring a
  clear recovery state.

## Validation

- Positive/negative tests cover every role/tool pair.
- Mid-run expiry, revocation, membership removal, course mismatch, policy
  change, and resource deletion fail closed.
- Unknown fields and caller-supplied trusted-context fields are rejected.
- Security review traces context from entry through the final tool execution.

## Supersedes

None.
