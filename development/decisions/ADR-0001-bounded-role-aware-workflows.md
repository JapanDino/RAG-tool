# ADR-0001 — Bounded role-aware agent workflows

Status: accepted

Date: 2026-08-02

## Context

The product already exposes deterministic services for course retrieval,
student tutoring, teacher audits and drafts, program intelligence, and Canvas
integration. A free-form autonomous planner would duplicate those services,
weaken their explicit guards, make behavior difficult to reproduce, and give
untrusted prompts too much influence over actions.

Users should experience one understandable Canvas assistant, while each role
still receives a distinct policy and bounded set of educational workflows.

## Decision

The product will implement a bounded workflow agent:

- an `AgentGateway` derives the exact trusted context and accepts a user goal;
- a `WorkflowRouter` selects only a versioned workflow from a closed enum;
- each workflow declares allowed roles, ordered/conditional steps, tools,
  budgets, evidence requirements, success states, and failure states;
- a model may classify intent or fill a validated workflow schema, but may not
  invent tools, steps, parameters, URLs, SQL, code, or system prompts;
- the server enforces maximum steps, tool calls, latency, tokens, retries, and
  output size;
- existing domain services remain the implementation of product actions.

The interface may call this one Canvas AI assistant. The trust boundary treats
learner, instructor, program, and administrator workflows separately.

## Alternatives considered

- General ReAct-style planner with arbitrary tools: rejected because imported
  course text and user prompts are untrusted and the product has consequential
  educational and Canvas boundaries.
- Separate unrelated chatbots per screen: rejected because it fragments the
  user experience and duplicates orchestration, observability, and evaluation.
- Fixed UI actions with no agent routing: safe but insufficient for the desired
  conversational assistant and multi-step role workflows.

## Consequences

### Positive

- Deterministic authorization and reproducible evaluation.
- Existing tutor/audit/program services remain reusable and independently
  testable.
- One assistant experience can grow without granting open-ended autonomy.
- Workflow versions can be compared in research and rolled back operationally.

### Negative

- New intents require a schema and workflow implementation.
- The assistant cannot satisfy arbitrary multi-step requests outside its
  supported educational tasks.
- Workflow design becomes an explicit product and evaluation responsibility.

## Validation

- Every workflow has allow/deny role tests and a maximum-step test.
- Unknown workflow/tool names and model-added parameters fail closed.
- Prompt and tool-output injection suites cannot escape the closed registry.
- Product metrics are recorded by workflow version.

## Supersedes

None.
