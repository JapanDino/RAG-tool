# M05 — Production pilot preflight

Status: done

## User outcome

Before involving the Canvas administrator, the deployment owner can run one
content-minimal command and see whether the application configuration is ready
for an external LTI rehearsal, which requirements are blocked, and which facts
still require human verification on the real school infrastructure.

## Users and permissions

- Deployment owner: supplies runtime environment through the approved secret
  manager and runs the local preflight command.
- Canvas administrator: later confirms Developer Key, deployment, and test-user
  facts outside this application.
- The command performs no mutation and grants no application permission.

## Context and evidence

- `development/ARCHITECTURE.md`: private signing material stays outside the app.
- `development/integrations/CANVAS.md`: first-pilot and access checklist.
- `development/security/SECURITY_BASELINE.md`: exact hosts, TLS, public-only JWKS,
  no credentials in output.
- `development/specs/done/M05-production-registration-readiness.md`: existing
  public-origin, JWKS, and platform-host validation remains canonical.
- `development/specs/done/M05-postgres-operational-rehearsal.md`: database
  rehearsal is a separate completed gate.

## Scope

- Add a reusable fail-closed production configuration assessment.
- Reuse the canonical LTI registration and product-session validators.
- Check production mode, external authentication, exact frontend/browser API/LTI
  HTTPS origins, public JWKS, platform allow-list, CSRF secret, and iframe
  cookie policy.
- Distinguish automated blockers from external/manual checks that cannot be
  proven without Canvas or the deployment host.
- Add a CLI that emits stable JSON with codes/statuses only and a nonzero exit
  code while blockers remain.
- Add an operator runbook and focused tests, including secret-redaction checks.

## Non-goals

- No DNS, TLS, HTTP, Canvas, agent-host, or database connection.
- No Developer Key creation, key generation, secret persistence, or deployment.
- No Canvas API read/write, roster sync, grades, or submissions.
- No claim that manual/external checks passed before real evidence exists.

## User flow

1. The deployment owner injects the proposed production environment locally.
2. They run the preflight command.
3. The command reports automated `passed`/`blocked` checks and explicit
   `external` checks without echoing configuration values.
4. Exit code `0` means local configuration is ready for an external rehearsal;
   a nonzero code means local blockers remain.

## UX contract

- JSON starts with one overall status and grouped check results.
- Each check contains only a stable code and status; no URL, key ID, host,
  client ID, database URL, or secret value appears.
- Missing external evidence is visibly `external`, not silently passed or mixed
  with local configuration failures.
- Human-readable operator documentation explains the next action for each code.

## Data and API

- No schema, migration, database, or HTTP API change.
- CLI output is versioned with `schema_version: 1`.
- Existing runtime configuration remains backward compatible.

## Security and privacy

- Never print environment values or exception strings that could contain them.
- Reject development/disabled auth and non-production mode.
- Reuse public-only RSA JWKS validation; never load private signing material.
- Perform no network request and no DNS resolution.
- Keep external verification truthful and pending until the real host exists.

## Acceptance criteria

- [x] Complete production-shaped configuration returns all local checks passed.
- [x] Missing/unsafe configuration returns stable blocker codes and exit code 2.
- [x] Output contains no supplied URL, host, key ID, client ID, or secret.
- [x] External Canvas/TLS/iframe/rollback checks remain explicitly unverified.
- [x] The command performs no network or database work.
- [x] Focused tests, full regression, and repository quality checks pass.

## Test plan

- Unit-test ready, missing, malformed, and secret-redaction cases.
- Test CLI exit codes and JSON schema in-process without real infrastructure.
- Run full backend regression and repo-wide pre-commit at batch close.
- General batch review after implementation.

## Batch review

- General quality recheck passed with no remaining P0/P1 findings.
- False-readiness cases for wildcard/malformed/loopback hostnames, browser-
  normalized decimal/octal/hex IPv4 aliases, and IPv4-mapped IPv6 loopback were
  fixed across CORS, frontend, browser API, and LTI tool origins.
- Private Canvas hosts must also appear in the primary exact-host allow-list.
- The operator runbook records that `NEXT_PUBLIC_API_BASE` must be preflighted
  before rebuilding the frontend with the same environment.
- Focused preflight suite: 66 passed.
- Full backend regression: 235 passed.
- Repo-wide pre-commit: passed.
