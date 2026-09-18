# Canvas PostgreSQL rehearsal

This rehearsal validates the local LTI persistence boundary before the first
real Canvas pilot. It never contacts Canvas and never uses the normal Compose
database or its volume.

## Run

Windows PowerShell:

    .\scripts\run-m05-postgres-rehearsal.ps1

Linux/macOS/CI:

    bash scripts/run-m05-postgres-rehearsal.sh

The command builds a minimal database-only Python runner, starts PostgreSQL 16
with pgvector on a tmpfs data directory, applies every migration twice, runs two
concurrency checks against the current source mounted read-only, and removes the
Compose project on exit. It now also races an instructor OAuth callback against
a replacement LTI session to verify the shared PostgreSQL lock order. OCR,
model, frontend, Redis, worker, and Canvas services
are not part of this rehearsal.

## Passing result

The one-shot runner prints JSON with:

- `status: passed`;
- six checked LTI/OAuth migrations;
- checked constraints and indexes;
- one candidate with `seen_count: 2` after simultaneous capture;
- one binding and one event after simultaneous resolution;
- one `bound` worker and one `candidate_unavailable` worker;
- `plaintext_cleared: true`.
- a consumed OAuth attempt with either a connected result or a bounded
  `callback_authorization_changed` result during simultaneous LTI relaunch.

The report contains counts and status codes only. It does not print platform
subjects, Canvas contexts, user IDs, course IDs, email addresses, or database
credentials.

The Python runner additionally requires both a database name containing
`rehearsal` or `test` and `M05_REHEARSAL_DISPOSABLE=1`. The Compose file owns
that confirmation; do not copy it into a production environment.

## What this does not prove

- Real Canvas claims, Developer Key policy, institutional SSO, TLS/DNS, iframe
  behavior, or browser cookie policy.
- Production backup, restore, failover, or capacity.
- Canvas API reads or writes; those remain outside M05.

Keep the live-host checklist blocked until the school supplies the Canvas
version, internal hostname, Developer Key process, SSO identity contract, and
approved signing-key owner.
