# B02 ModelGateway foundation

Status: done

## User outcome

An authorized administrator can tell whether the Canvas agent model boundary is
disabled, safely configured, degraded, or ready without seeing credentials or
provider internals, while future workflows receive one validated, bounded
OpenAI-compatible inference service for approved DeepSeek/Gemma deployments.

## Users and permissions

- Administrator: inspect content-free model readiness and aggregate runtime
  health for their organization.
- Learner, instructor, methodologist, and program designer: no model
  configuration or health access in this slice.
- Application services: invoke only a server-selected task configuration.
- No user or model may choose provider origin, credential, system prompt,
  unrestricted model ID, or operational limit.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B02.
- `development/specs/done/B00-agent-contract-freeze.md`.
- `development/agent/API_CONTRACT.md`.
- `development/agent/TOOL_CATALOG.md`.
- `development/decisions/ADR-0003-agent-host-model-boundary.md`.
- `development/ARCHITECTURE.md` and security baseline.
- Existing `openai_client.py`, `llm_provider.py`, tutor, and Copilot callers.

## Scope

- Implement a central OpenAI-compatible `ModelGateway` with injectable transport
  and server-owned task configuration.
- Support DeepSeek/Gemma-shaped chat-completion responses through the same
  validated contract without hard-coding provider-specific product behavior.
- Add bounded connect/read timeout, retry, concurrency, input/output token, and
  response-size limits.
- Add closed structured-output validation and deterministic disabled/unavailable
  fallback semantics.
- Record content-free invocation metadata: task/workflow/prompt version,
  configured model alias, latency, token counts when supplied, failure class,
  validation result, and fallback.
- Add an administrator-only, organization-scoped readiness/runtime-health API
  projection with no secrets, raw prompts, responses, or personal content.
- Add a Workshop Route administrator readiness card only if it can reuse the
  current integration workspace without exposing engineering jargon to learners.
- Leave existing tutor/Copilot callers on their current paths in this slice;
  define the incremental adapter seam rather than a repository-wide migration.

## Non-goals

- AgentGateway messages, workflow routing, tool execution, model-selected tools,
  multi-turn memory, or Canvas writes.
- Real provider credentials or calls to the organization host.
- User-selectable provider/model/temperature/system prompt.
- Migrating all legacy LLM/embedding callers.
- Claiming model quality from mocked compatibility tests.

## User flow

1. Administrator opens the existing protected integration/operations surface.
2. The product shows one bounded model-contour state and safe next action.
3. A mocked application workflow invokes the gateway with a server-owned task.
4. Valid structured output returns metadata; invalid/outage cases produce a
   deterministic bounded failure without leaking provider details.

## UX contract

- Readiness language describes product capability: unavailable, setup required,
  degraded, or ready.
- Do not show API keys, base URLs, raw model identifiers, prompts, token dumps,
  stack traces, or provider response bodies.
- Show last bounded check, latency/failure aggregate, and one administrator
  recovery action when applicable.
- Loading, disabled, misconfigured, unavailable, degraded, ready, and permission
  states are explicit; no model call is triggered merely by rendering the card.
- Desktop/mobile, keyboard, focus, contrast, reduced-motion, and clean-console
  checks apply if the card is implemented.

## Data and API

- Add versioned Pydantic input/output/readiness schemas.
- Prefer a small content-free invocation table only if required for durable
  health; otherwise specify the migration and persistence boundary before code.
- Request bodies never accept provider origin, secret, model, workflow policy,
  system prompt, or trusted identity/course fields.
- Readiness is configuration validation; an explicit bounded probe is separate
  and never runs on GET/page render.
- Existing environment names remain backward compatible; new agent-host settings
  are server-only and documented with safe placeholders.

## Security and privacy

- Exact allow-listed HTTPS origin outside local tests; block arbitrary/private
  addresses unless an explicit deployment allow-list approves the host.
- Secrets stay in environment/secret custody and are redacted from exceptions,
  logs, schemas, health, tests, and Markdown.
- Do not persist raw prompts, responses, authorization headers, course excerpts,
  student data, or chain-of-thought in invocation metadata.
- Structured output is untrusted until schema validation passes.
- Provider outage/invalid JSON/oversize/rate limit cannot bypass policy or fall
  through to unvalidated text.

## Acceptance criteria

- [x] DeepSeek- and Gemma-shaped mocked responses pass one shared structured
  gateway contract.
- [x] Missing/invalid config, timeout, rate limit, invalid JSON/schema, oversized
  response, retry exhaustion, and disabled mode produce stable bounded outcomes.
- [x] User input cannot select model, origin, credential, system prompt, or
  operational limits.
- [x] Invocation metadata is content-free, bounded, and secret-safe.
- [x] Only an organization administrator can inspect readiness/runtime health;
  every other role and cross-organization request fails non-disclosingly.
- [x] Existing tutor/Copilot behavior and full relevant regression suite remain
  green.
- [x] If UI changes, desktop/mobile visual and accessibility checks pass with
  fresh screenshots.
- [x] Batch-quality, agent-safety, RAG, and product-UX reviews have no open P0/P1.

## Test plan

- Unit: configuration, budgets, response parsing, validation, retry/failure
  mapping, redaction, metadata, and DeepSeek/Gemma compatibility.
- Service/API: administrator allow; every role/cross-org deny; no call on GET;
  safe readiness and degraded states.
- Security: credential-shaped values, malicious provider body, oversized JSON,
  injected task/model/origin fields, and log/schema scans.
- Frontend/browser if applicable: all readiness states, desktop/mobile, keyboard,
  clean console, no overflow, and no network probe on render.
- Regression: focused model/tutor/Copilot/identity tests, full pytest, frontend
  lint/build if changed, pre-commit, and `git diff --check`.
- Batch review: batch quality, agent safety, and RAG evaluator in parallel.

## Batch review

Completed on 2026-08-02. `ModelGateway` now accepts only a closed server-owned
task, validates DeepSeek/Gemma-shaped OpenAI-compatible envelopes into a strict
Pydantic schema, and returns deterministic fallback metadata for disabled,
configuration, timeout, rate-limit, capacity, circuit, response-size, envelope,
and schema failures. Exact approved origins include scheme and effective port;
redirects are rejected and response bodies are streamed under an early byte
cap. Operational floats must be finite, provider token counts are type-checked
and clamped before PostgreSQL persistence, and credentials are omitted from
configuration representations.

Migration `0039` stores organization-scoped content-free invocation events. The
administrator-only, no-store readiness endpoint rejects compatibility bypass
and every non-admin/cross-organization request. Rendering the readiness card
never probes the provider. The Workshop Route card is integrated into the
existing Canvas operations page and distinguishes configured, ready, degraded,
disabled, refresh-error, and stale states with product language, four aggregate
metrics, visible recovery guidance, and no provider name, URL, credential,
prompt, response, transcript, or individual-level signal.

Initial independent reviews found P1 issues in provider token bounds, exact
origin/redirect/stream limits, finite timeouts, small-sample p95, secret repr,
compatibility bypass, stale refresh presentation, route-state semantics,
administrator vocabulary, missing failed counts, stale age, and small type.
All were fixed. Targeted batch-quality, agent-safety, RAG, and product-UX
rechecks reported no remaining P0/P1.

Verification evidence: 28 focused ModelGateway tests; 341 full backend tests;
frontend lint and production build; desktop/mobile browser coverage for all
readiness/recovery states, keyboard retry, stale labeling, console cleanliness,
and overflow; full signed Canvas learner/instructor regression; all-files
pre-commit and `git diff --check`. Screenshots live under
`output/playwright/b02-model-gateway/`. No real provider, organization host,
school Canvas, deployment, commit, push, or publication was used.

Deferred P2: mocked envelopes do not prove real DeepSeek/Gemma quality or host
compatibility; model concurrency/circuit state is process-local; the 500-event
health window has no truncation flag; migration `0039` still needs a clean and
existing-data PostgreSQL rehearsal; invocation retention/purge and cost budgets
belong to the hosted operations batches; explicitly allow-listed hosts still
have DNS rebinding/TOCTOU residual risk; input/output safety is independently
bounded by characters, bytes, schema, and server-selected `max_tokens`, not by a
local provider tokenizer.
