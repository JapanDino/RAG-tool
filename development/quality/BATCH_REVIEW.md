# Batch review

A batch review runs once after one vertical slice meets its acceptance criteria.
It is not a review of every intermediate edit.

## Batch size

A healthy batch:

- delivers one observable user outcome;
- usually takes two to five working days;
- contains at most one substantial migration;
- can be demonstrated from entry point to result;
- has focused tests before full review.

Split a batch when unrelated roles, migrations, or integrations make the user
outcome difficult to explain.

## Review sequence

1. Freeze the intended diff and active spec.
2. Run the full automated quality gate.
3. Run `batch-quality-reviewer`.
4. If UI changed materially, run `product-ux-reviewer` with screenshots.
5. If RAG/model behavior changed, run `rag-evaluator`.
6. Group findings by severity.
7. Fix P0 and P1 findings.
8. Perform one targeted recheck, not an unlimited review loop.
9. Update `development/STATUS.md` once.

## Severity

- P0: security, privacy, data loss, or unusable core flow; blocks completion.
- P1: likely user-facing defect or unmet acceptance criterion; fix in batch.
- P2: meaningful improvement with tolerable deferral; record explicitly.
- P3: minor polish or preference; do not delay the batch by default.

## Reviewer input

- active spec;
- repository status and diff;
- relevant architecture/design/security document;
- test/build output;
- screenshots for UI changes;
- benchmark comparison for RAG changes.

## Reviewer output

    Summary
    Acceptance criteria: pass/fail
    P0/P1 findings with file and line evidence
    P2 deferred work
    Tests and checks run
    Residual risk

Avoid broad rewrites, style-only complaints, or hypothetical features outside
the active spec.

## Time budget

- General review: 30–60 minutes.
- UX review: 30–45 minutes.
- RAG evaluation review: 30–60 minutes.
- One fix pass and one targeted recheck.

If review repeatedly exceeds this budget, reduce batch size or strengthen
automated checks.
