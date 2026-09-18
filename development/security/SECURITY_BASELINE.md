# Security baseline

These rules are non-negotiable unless an explicit threat-model decision replaces
them.

## Credentials

- Store secrets only in approved environment or secret-management systems.
- Never put tokens in Markdown, prompts, agent settings, allow-listed commands,
  fixtures, screenshots, logs, or git history.
- Rotate a credential immediately after suspected exposure.
- Keep provider and Canvas tokens scoped and short-lived where supported.

## Identity and authorization

- Deny by default.
- Enforce permissions in backend services and routes.
- Separate organization, course, role, and resource visibility.
- Do not rely on frontend hiding.
- Audit membership and role changes.

## Student protection

- Minimize collected student data.
- Avoid psychological, ability, or disciplinary profiling.
- Prefer aggregate administrative analytics.
- Define retention and deletion rules before a student pilot.
- Require a documented lawful/organizational basis for data involving minors.

## AI boundaries

- Treat retrieved content and model output as untrusted.
- Validate structured output and citation membership server-side.
- Do not give the model raw credentials or unrestricted LMS/database tools.
- Restrict assessment assistance by teacher-configured policy.
- Require human confirmation for course changes, grades, messages, and other
  consequential actions.

## Import and Canvas

- Validate content type, size, filenames, and extracted text.
- Keep SSRF protections for arbitrary URLs.
- Permit an internal Canvas host only through exact configuration, TLS trust,
  redirect controls, and resolved-address validation.
- Never solve local integration by globally allowing private networks.
- Treat LTI registration drafts as inert data: draft save performs no DNS lookup
  or fetch, and activation applies exact host and resolved-address checks.
- Publish only bounded RSA signing members in the tool JWKS. Reject private JWK
  fields and keep the corresponding private signing material outside the app.

## Agent safety

- Reviewer agents are read-only.
- Commit, push, deploy, and write-back require explicit user intent.
- Direct edits to environment and lock files are prohibited.
- Shell allow-lists must not contain credentials.
