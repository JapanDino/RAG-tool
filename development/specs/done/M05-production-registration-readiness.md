# M05 — Production LTI registration readiness

Status: done

## User outcome

An organization administrator can prepare a minimal Canvas LTI 1.3
configuration package, see exactly what infrastructure is still missing, save
the exact platform identifiers as an inactive draft, and deliberately activate
the registration only after endpoint trust checks pass. The workflow works in
local preview without Canvas or deployment access and never claims that the
school LMS is connected before a real launch succeeds.

## Users and permissions

- Only an active organization `administrator` can list, create, edit, activate,
  or deactivate production registrations for that organization.
- Other roles and cross-organization administrators receive non-disclosing 404s.
- Public Canvas configuration and tool JWKS endpoints expose only deliberate
  public metadata and public RSA keys.
- Course-scoped LTI product sessions cannot enter this organization-level flow.

## Context and evidence

- `development/specs/done/M05-local-lti-launch-boundary.md` verifies signed OIDC
  launch and exact platform bindings.
- `development/specs/done/M05-role-scoped-product-session.md` verifies the
  short-lived course-scoped product session.
- Canvas documents that account administrators can use a raw JSON configuration
  or a configuration URL; it requires OIDC initiation and target-link URLs plus
  a public JWK or JWK URL.
- LTI Core 1.3 separates registration (`client_id`) from deployments and requires
  a distinct immutable `deployment_id` for every deployment.

## Scope

- Configure one public tool origin through `LTI_TOOL_PUBLIC_URL`; production
  requires an exact HTTPS origin, while safe development may use loopback HTTP.
- Parse `LTI_TOOL_JWKS_JSON` as a public-only RSA/RS256 JWKS. Reject private key
  fields, duplicate/missing `kid`, excessive keys, malformed values, and unsafe
  production fallback.
- Expose cacheable public endpoints:
  - `GET /integrations/lti/configuration` — minimal Canvas course-navigation
    JSON with no LTI Advantage scopes and `privacy_level: anonymous`;
  - `GET /integrations/lti/jwks` — current public keys with deterministic ETag
    and conditional 304 support.
- Expose administrator readiness and registration APIs scoped to one
  organization.
- Create registrations inactive by default. Derive the tool launch URL
  server-side; never accept it from the browser.
- Allow configuration edits only while inactive. Activation is explicit and
  runs current origin, endpoint, DNS/private-host allow-list, identifier, and
  public-key readiness checks.
- Deactivation immediately blocks new login/launch resolution but preserves
  bindings and audit history.
- Record content-minimal create/update/activate/deactivate audit events with
  actor, organization, registration ID, changed field names, and time.
- Add an administrator page linked from `/workspace` with a readiness rail,
  copyable Canvas JSON, draft form, registration list, and plain next steps.

## Non-goals

- No Canvas API call, Developer Key creation, OAuth token, roster/content sync,
  LTI Advantage scope, grades, messages, or LMS write.
- No private signing key generation, upload, display, storage, or rotation.
- No dynamic registration protocol and no automatic trust of launch claims.
- No production subject/context provisioning; existing explicit bindings remain
  required before a launch can resolve product access.
- No promise that iframe cookies, internal TLS, DNS, or the self-hosted Canvas
  version work before the real environment is tested.

## Admin flow

1. Open `Подключение Canvas` from the administrator workspace.
2. Inspect the readiness rail: public origin, public keys, Canvas JSON, and
   missing external checks.
3. Copy the raw JSON or configuration URL for the Canvas administrator.
4. After Canvas creates/enables and deploys the Developer Key, enter the exact
   issuer, client ID, deployment ID, authorization endpoint, and platform JWKS
   URL.
5. Save an inactive draft. The page says that no launch is accepted yet.
6. Activate explicitly. Failed trust checks preserve the draft and identify the
   field to correct without revealing internal network details.
7. See the active registration plus binding counts and the truthful next step:
   bind known users/course contexts, then perform a real signed launch.

## UX contract

- The page is an installation checklist, not a generic settings dashboard.
- One readiness rail connects four factual stops: tool address, public key,
  Canvas registration, first verified launch.
- `Готово локально`, `Нужна инфраструктура`, `Черновик`, and `Активна` always
  include text; color is not the only signal.
- Raw JSON is collapsed by default on mobile and copy feedback uses an accessible
  live region.
- Activation and deactivation state exactly what changes. Neither implies
  Canvas synchronization.
- Loading, empty, validation, permission, copy-unavailable, activation failure,
  success, and partial-readiness states have one valid next action.
- Desktop 1440 px and mobile 390 px have no horizontal page overflow; long URLs
  wrap and every action is keyboard accessible.

## Data and API

- Migration `0035_lti_registration_events.sql` adds content-minimal audit events.
- `GET /integrations/lti/configuration` returns the tool configuration only when
  public tool metadata is structurally ready.
- `GET /integrations/lti/jwks` supports `ETag`/`If-None-Match` and exposes no
  private field.
- `GET /integrations/lti/organizations/{organization_id}/readiness` returns tool
  endpoints, public-key IDs, blockers/warnings, and a safe Canvas JSON preview.
- `GET /integrations/lti/organizations/{organization_id}/registrations` lists
  production registrations, explicit subject/context counts, and aggregate
  verified-launch count/time without launch identities.
- `POST /integrations/lti/organizations/{organization_id}/registrations` creates
  an inactive draft.
- `PATCH /integrations/lti/organizations/{organization_id}/registrations/{id}`
  edits an inactive draft or explicitly changes active state.
- No request or response contains a Canvas token, private JWK, API credential,
  session credential, or hidden course content.

## Security and privacy

- Tool public origin and platform endpoints reject credentials, fragments,
  unsupported schemes, and ambiguous URL forms.
- Activation applies exact host allow-lists and explicit private-host rules;
  draft saving performs no server-side fetch and cannot become an SSRF primitive.
- JWKS accepts only public RSA signing members and uses bounded JSON/key sizes.
- The configuration requests no Canvas service scopes and uses anonymous
  placement privacy; LTI `sub`, context, and roles still pass through the
  signed launch as defined by Canvas/LTI.
- Production development registrations stay unavailable. New production
  registrations never provision users, memberships, courses, or bindings.
- Audit records contain changed field names, never endpoint values or identifiers.

## Acceptance criteria

- [x] Local administrator sees a truthful readiness page without Canvas access.
- [x] Public configuration contains only the minimal course-navigation placement,
      empty scopes, anonymous privacy, and server-derived HTTPS endpoints.
- [x] Public JWKS rejects private material and supports multiple public keys,
      deterministic ETag, conditional 304, and rotation-safe key IDs.
- [x] Only the organization administrator can create an inactive draft, and
      cross-organization/other-role requests fail without disclosure.
- [x] An inactive draft cannot accept login/launch; an active validated
      registration can enter the existing launch boundary.
- [x] Active configuration fields cannot be silently edited; deactivate first.
- [x] Endpoint/private-host validation happens on activation, not draft save.
- [x] Create/update/activate/deactivate audit records contain no configuration
      values or secrets.
- [x] UI loading, empty, invalid, activation failure/success, copy, desktop,
      mobile, overflow, keyboard, and clean-console states pass.
- [x] Existing local issuer, product-session, and development identity flows
      remain functional.

## Test plan

- Unit: tool origin, bounded public JWKS, private-field rejection, Canvas JSON,
  ETag stability/rotation, structural draft validation, activation trust checks.
- API: public configuration/JWKS, permission isolation, inactive create,
  inactive edit, activate/deactivate, active-edit refusal, duplicate handling,
  audit redaction, binding counts, existing launch regression.
- Frontend: readiness/empty/draft/active/error/copy states at desktop/mobile,
  keyboard/focus, long URLs, console and network inspection.
- Regression: full backend suite, frontend lint/build, repo-wide pre-commit, and
  `git diff --check`.

## Batch review

Passed after one targeted fix/recheck cycle. General/security review found and
closed row-mutation serialization, non-global/multicast endpoint policy,
required exact host allow-list, malformed URL normalization, and unexpected
request-field handling. Product UX review found and closed independent partial-
readiness states plus confirmation/error focus recovery. No P0/P1 remains.

Final evidence: 153 backend tests, frontend lint/build, repo-wide pre-commit,
`git diff --check`, desktop/mobile overflow and clean-console checks, and real
browser draft, failure, edit, activation, confirmation-focus, and cancel-focus
flows pass.
