# Canvas pilot preflight

This gate answers one narrow question: is the proposed application runtime
configuration locally ready for a real external LTI rehearsal? It performs no
network, DNS, database, Canvas, or deployment action.

## Run

Inject the proposed production environment through the approved local secret
mechanism, then run from the repository root:

    python scripts/check_lti_pilot_preflight.py

Run the preflight before rebuilding the frontend and supply that rebuild with
the same `NEXT_PUBLIC_API_BASE`; the value is compiled into the Next.js bundle,
so changing only the shell environment cannot repair an older image.

Exit code `0` and `status: ready_for_external_rehearsal` mean every automated
local check passed. Exit code `2` and `status: blocked` mean at least one local
configuration blocker remains. The JSON contains status codes only and is safe
to attach to an internal readiness ticket; it never prints origins, hosts,
public-key contents or IDs, client IDs, database URLs, or secret values.

## Automated check codes

- `production_environment`: `APP_ENV` is exactly `production`.
- `external_authentication`: `AUTH_MODE` is exactly `external`.
- `cors_https_origins`: at least one exact HTTPS CORS origin, never `*`.
- `frontend_https_origin`: the launch destination is an exact HTTPS origin.
- `browser_api_https_origin`: the API origin compiled into the frontend is an
  exact HTTPS origin, never the local Docker default.
- `frontend_origin_allowed_by_cors`: the frontend is credential-enabled.
- `tool_public_origin`: the Canvas-facing tool origin passes canonical LTI
  validation.
- `tool_public_jwks`: one to five public-only RSA/RS256 keys pass canonical LTI
  validation; private JWK fields are rejected.
- `platform_host_allowlist`: at least one exact Canvas platform host is present.
- `private_platform_host_scope`: every explicitly permitted private host is also
  present in the primary exact-host allow-list.
- `iframe_cookie_policy`: production uses a Secure, SameSite=None, `__Host-`
  product-session cookie.
- `session_csrf_secret`: the production CSRF secret meets the runtime minimum.

Do not paste a failing environment into a ticket. Fix it through the deployment
secret/configuration owner and rerun the content-minimal report.

## External checks

The following codes always remain `external` because local code cannot prove
them truthfully:

- Canvas version and topology;
- enabled Developer Key/deployment;
- institutional DNS and TLS chain;
- real iframe and browser-cookie behavior;
- student and instructor test accounts;
- a non-sensitive pilot course;
- signing-key ownership and rotation;
- rollback owner and trigger;
- approved student-data retention.

Record those facts in the school's normal change-management system. Do not add
credentials, private keys, tokens, learner identifiers, or account passwords to
this repository or its Markdown files.

## Rollback boundary

Before the first launch, the school must name an owner who can disable the
Canvas Developer Key/deployment and an application owner who can deactivate the
matching registration. A failed local preflight, signature validation,
role/context mapping, iframe check, or privacy check is a stop condition. The
first pilot still has no Canvas API writes, grades, submissions, or roster sync.
