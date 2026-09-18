# ADR-0003 — Organization agent-host model boundary

Status: accepted

Date: 2026-08-02

## Context

The organization can host OpenAI-compatible models such as DeepSeek and Gemma.
Current model access is distributed across annotation, tutor, and remediation
services. The Canvas agent needs consistent routing, validation, budgets,
fallback, observability, and secret custody without exposing provider details to
users or allowing models to become the authorization boundary.

## Decision

All new agent workflows use one server-side `ModelGateway` with task-specific
configuration. The gateway:

- speaks an OpenAI-compatible HTTP contract to approved exact origins;
- keeps API keys, base URLs, and network allow-lists in the deployment secret
  boundary, never Markdown, frontend bundles, prompts, or events;
- selects provider/model from server configuration and workflow policy, not
  message input;
- validates structured output against versioned schemas;
- records provider, model, prompt/workflow version, latency, token counts,
  estimated cost, failure class, and fallback without raw credentials;
- enforces connection/read timeouts, bounded retries, concurrency, token, and
  cost limits;
- returns deterministic or explicitly unavailable behavior when the provider
  fails.

Retrieval, authorization, policy, citation membership, evidence visibility,
approval, database writes, and Canvas transport remain outside the model and
gateway.

Existing model callers migrate incrementally; this ADR does not authorize a
repository-wide rewrite.

## Alternatives considered

- Let each feature call a provider directly: rejected because limits,
  observability, validation, and fallback drift across features.
- Expose provider/model selection to end users: rejected because it leaks
  infrastructure details and defeats task-specific evaluation and budgets.
- Run the agent inside the model host: rejected because identity, Canvas, data,
  and approval boundaries must remain in the application.

## Consequences

### Positive

- DeepSeek/Gemma can be evaluated and replaced without changing product tools.
- One place enforces operational limits and records comparable metrics.
- Provider outages cannot bypass evidence or authorization policy.

### Negative

- The gateway becomes a reliability-critical application component.
- Existing callers temporarily coexist with the new path during incremental
  migration.
- Accurate token/cost accounting may require provider-specific normalization.

## Validation

- Contract tests cover DeepSeek/Gemma-shaped OpenAI-compatible responses,
  invalid JSON, timeout, retry, rate limit, oversized output, and unavailable
  provider behavior.
- Tests prove request input cannot change provider, model, origin, or system
  prompt.
- Logs/events are scanned for configured credentials and raw authorization
  headers.
- Candidate models are compared on frozen task-specific evaluation sets.

## Supersedes

None.
