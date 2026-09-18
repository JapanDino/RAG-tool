# M05 — PostgreSQL operational rehearsal

Status: done

## User outcome

The project team can run one disposable command before a real Canvas pilot and
prove that LTI migrations, unique constraints, row locks, and explicit binding
resolution behave on PostgreSQL rather than relying on SQLite approximations.

## Scope and safety boundary

- Use a dedicated Compose project and an ephemeral PostgreSQL data directory.
- Apply all migrations in lexical order, then run the migration command again
  to prove checksum-backed idempotency.
- Inspect the applied `0033`–`0036` schema and required PostgreSQL indexes.
- Exercise simultaneous first capture of one verified opaque subject.
- Exercise simultaneous resolution of one pending candidate by two
  administrators/targets and prove exactly one binding and event wins.
- Produce content-minimal machine-readable results and a short operator command.
- Never contact Canvas, the organization agent host, or a production database.

## Non-goals

- Real Canvas Developer Key, SSO, TLS, DNS, iframe, or browser-cookie testing.
- Canvas API reads, roster sync, grade access, or LMS writes.
- Load, soak, failover, backup, or disaster-recovery testing.
- Rehearsing unrelated M01–M04 concurrency paths in this batch.

## Technical contract

- `docker-compose.rehearsal.yml` contains only an ephemeral PostgreSQL service
  and a one-shot rehearsal runner.
- The runner refuses non-PostgreSQL URLs and database names without an explicit
  rehearsal/test marker.
- Concurrent capture must converge to one pending candidate with a repeat count
  of two; a unique race must not escape as an unhandled server error.
- Concurrent bind must produce one `bound` result and one safe
  `candidate_unavailable` conflict, one subject binding, one binding event, and
  cleared candidate plaintext.
- Output must contain counts and status codes only, never opaque identifiers.

## Acceptance criteria

- [x] All migrations apply to an empty PostgreSQL 16/pgvector database.
- [x] A second migration pass skips every applied file without drift.
- [x] Migrations `0033`–`0036` and their critical indexes/constraints are present.
- [x] Simultaneous first capture is deduplicated without an uncaught integrity error.
- [x] Simultaneous binding serializes to exactly one winner and one safe loser.
- [x] The rehearsal leaves no persistent database volume or exposed service port.
- [x] Unit regression, rehearsal command, and repository quality checks pass.

## Test plan

- Existing SQLite tests remain the fast functional regression gate.
- The one-shot runner uses two independent SQLAlchemy sessions and thread
  barriers against PostgreSQL.
- Compose runs migrations twice before the runner.
- Batch review inspects database safety guards, race handling, output content,
  and cleanup behavior.

## Batch review

- General quality recheck: passed with no remaining P0/P1 findings.
- Fresh disposable PostgreSQL replay passed after the safety fixes: all 36
  migrations applied and skipped on replay; the schema check reported 4
  migrations, 11 constraints, and 3 indexes; both concurrency races passed.
- The database-name guard rejects substring-only names such as `latest` and
  `contest_production`.
- Bash and PowerShell wrappers fail closed when a main step or cleanup fails.
- Cleanup verification found zero rehearsal containers and zero rehearsal
  volumes; the Compose configuration publishes no database port.
- `python -m pytest -q`: 169 passed.
- `pre-commit run --all-files`: passed.
