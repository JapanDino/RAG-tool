# B10C Model-host preflight handoff

Status: complete

## User outcome

An organization administrator can choose a DeepSeek- or Gemma-compatible host
profile, inspect what is already verifiable offline, and download a
credential-free handoff bundle for the system administrator before any real
school host is connected.

## Users and permissions

- Organization administrators may inspect and export their organization handoff.
- Every other role, cross-organization identity, anonymous request, and
  compatibility bypass receives a non-disclosing denial.
- The system administrator consumes the exported bundle outside the product and
  supplies credentials only through deployment secret custody.

## Context and evidence

- `development/decisions/ADR-0003-agent-host-model-boundary.md`.
- `development/specs/done/B02-model-gateway-foundation.md`.
- `development/specs/done/B10B-admin-agent-policy-control-plane.md`.
- `development/design/DESIGN_SYSTEM.md`.
- Existing `model_gateway_configuration` is the single configuration validator.

## Scope

- Two versioned compatibility profiles: DeepSeek OpenAI-compatible and Gemma
  OpenAI-compatible.
- Offline validation of committed synthetic response envelopes through the
  production structured-output parser.
- Content-free server configuration checks based on presence and safe validation,
  never serialized values.
- Explicit external checks that cannot be completed without the approved host.
- Administrator-only no-store report and JSON download endpoints.
- A CLI that emits the same safe bundle without network or database access.
- A Workshop Route handoff passport in the Canvas integration workspace.

## Non-goals

- Network access, DNS lookup, TLS handshake, provider authentication, or a real
  model request.
- Storing or exporting API keys, base URLs, hostnames, model IDs, prompts,
  responses, authorization headers, or course content.
- Claiming model quality, latency, availability, or production compatibility.
- Letting a user select the deployed model or alter runtime budgets.

## User flow

1. Administrator opens `Паспорт подключения AI-сервиса`.
2. They choose the DeepSeek or Gemma compatibility family.
3. The product separates locally passed, blocked configuration, and external
   checks with an explicit owner for each.
4. `Скачать пакет для системного администратора` downloads the exact safe JSON
   artifact and shows its short fingerprint.

## UX contract

- Subject: a Canvas Letovo administrator preparing a handoff to infrastructure.
- Single job: understand what is known now and transfer the remaining checklist.
- Palette and type reuse the canonical Workshop Route tokens.
- Layout is a three-stamp passport: local contract, server configuration, external
  rehearsal. Numbering is chronological, not decorative.
- Signature: a perforated handoff receipt with a deterministic fingerprint.
- Loading, disabled/setup, misconfigured, configured, deterministic-only policy,
  download busy/error/success, permission, desktop, and mobile states are clear.
- Profile controls expose families only; no exact model or infrastructure value.
- Visible focus, keyboard operation, `aria-live`, and reduced-motion apply.

## Data and API

- No migration and no persistence.
- GET `/organizations/{organization_id}/agent-model/preflight?profile=...`.
- GET `/organizations/{organization_id}/agent-model/preflight/export?profile=...`.
- Profile IDs are closed literals and schema-versioned.
- Report and export share one deterministic projection and fingerprint.
- CLI: `python scripts/check_agent_model_preflight.py --profile deepseek|gemma`.

## Security and privacy

- Reuse administrator organization authorization and reject bypass principals.
- Assessment performs no socket, HTTP, DNS, file, model, or Canvas operation.
- Environment values influence only closed passed/blocked state codes.
- Export allow-list is schema-owned; unknown fields cannot enter the artifact.
- Response and download headers are no-store and nosniff.
- A credential-shaped sentinel must be absent from API, CLI, frontend, bundle,
  logs, and filenames.

## Acceptance criteria

- [x] Both profiles pass the same offline structured-envelope contract.
- [x] Missing, unsafe, and configured server states produce bounded truthful
  reports without values.
- [x] The report distinguishes local checks from external host validation and
  says that no network probe or course data was used.
- [x] Export and CLI are byte-stable for the same inputs and contain no secret,
  origin, hostname, model ID, prompt, or response body.
- [x] Only an exact organization administrator can inspect or export.
- [x] UI supports profile change, safe download, failure recovery, keyboard,
  desktop, and mobile without overflow or console errors.

## Test plan

- Unit: profile registry, fixture parsing, configuration states, fingerprint,
  deterministic serialization, and secret/value scanning.
- API: administrator allow; role/cross-org/bypass deny; headers and attachment.
- CLI: both profiles, exit states, output equivalence, no network, and no secret.
- Browser: two profiles, setup/configured/error/download, focus, desktop/mobile,
  overflow, and clean console.
- Full pytest, pre-commit, frontend lint/build, and Canvas Playwright regression.

## Batch review

- General quality, product UX, and agent/RAG safety reviewers passed the final
  targeted recheck with no remaining P0/P1 findings.
- Review fixes separated origin from runtime diagnostics, moved profile
  validation after authorization, bounded malformed dormant URLs, preserved
  keyboard focus, kept report/export profile identity coherent after failure,
  and corrected stage-specific counts.
- Final evidence: 461 backend tests, repo-wide pre-commit, frontend lint/build,
  104/104 Canvas simulator scenarios, and focused 34 backend plus 10 browser
  rechecks.
- Deferred P2: reconstruct the browser download from a deep client allow-list;
  add hover polish, a dedicated misconfigured screenshot, and a full-page LTI
  placement screenshot; clarify which exported server fields have safe defaults.
- Residual boundary: no real model host, credentialed probe, school network,
  TLS chain, or school Canvas instance was tested.
