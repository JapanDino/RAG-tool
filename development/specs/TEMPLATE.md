# [Milestone] Feature name

Status: draft

## User outcome

Describe the observable result for one user role.

## Users and permissions

List the roles involved and the actions each role may perform.

## Context and evidence

Link the relevant product, architecture, design, security, and integration
documents. Record verified current behavior instead of assumptions.

## Scope

- Included behavior.
- Included API, data, and UI changes.

## Non-goals

- Explicitly excluded behavior.
- Follow-up work that must not expand this batch.

## User flow

1. Entry point.
2. Main action.
3. Evidence or confirmation.
4. Success result.

## UX contract

Define:

- information hierarchy;
- desktop and mobile behavior;
- loading, empty, error, permission, low-confidence, and success states;
- exact primary action labels;
- accessibility requirements.

## Data and API

- schema or migration changes;
- endpoints and request/response contracts;
- backward-compatibility expectations;
- versioning and audit requirements.

## Security and privacy

- authorization checks;
- trust boundaries;
- sensitive data;
- abuse and prompt-injection cases;
- logging and retention rules.

## Acceptance criteria

- [ ] Criterion expressed as observable behavior.
- [ ] Negative permission case.
- [ ] Failure/recovery case.
- [ ] Relevant metrics or events.

## Test plan

- unit;
- service;
- API;
- browser/E2E;
- regression;
- manual visual check.

## Batch review

Record only final P0/P1 resolution and material deferred work. Do not turn this
section into a chronological work log.
