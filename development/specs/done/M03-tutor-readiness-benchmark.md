# M03 — Student tutor readiness benchmark

Status: done

## User outcome

A school administrator, methodologist, or instructor can run the existing
course Evaluation Protocol and receive a reproducible pass/fail readiness result
for the student tutor before enabling a Canvas pilot.

## Users and permissions

- Instructor, methodologist, and administrator: run, view, and download the
  course evaluation protocol.
- Program designer: view existing protocols but cannot create a new run.
- Student and outsiders: no access to evaluation protocols or case details.

## Context and evidence

- `development/STATUS.md`: no committed tutor benchmark exists yet.
- `development/PRODUCT.md`: administrators need aggregate latency and quality
  signals; methodologists need inspectable evidence rather than opaque scores.
- `development/ARCHITECTURE.md`: tutor answers remain constrained by the
  PolicyEngine, course evidence, and student-visible content.
- The existing Evaluation Protocol already stores versioned thresholds, dataset
  hash, checks, metrics, methodology, and downloadable JSON/Markdown artifacts.

## Scope

- Add a committed, synthetic, bilingual student-tutor regression dataset.
- Reuse production lexical normalization, candidate cap, hybrid scoring,
  threshold, module bonus, per-document diversity, and assessment guard logic so
  benchmark and runtime behaviour cannot silently drift apart.
- Measure retrieval Recall@K, MRR, unsupported-query abstention, assessment guard
  accuracy, labeled citation-support proxy, and offline per-case p95 latency.
- Add the tutor metrics and a required course-scoped student-visible retrieval
  smoke as checks in Evaluation Protocol v2.
- Keep the synthetic gate deterministic, but run the course smoke with the
  effective deployment provider, threshold, and candidate cap; store both
  configurations separately.
- Provide a local/CI command that writes versioned JSON and Markdown reports and
  exits non-zero in strict mode when a required threshold fails.
- Keep case-level diagnostics free of real student questions or course content.

## Non-goals

- Calling DeepSeek, Gemma, or another hosted model during the deterministic
  quality gate.
- Claiming that lexical labeled support proves semantic answer entailment.
- Measuring network/model latency, token cost, or production concurrency.
- A teacher-facing benchmark editor or arbitrary threshold controls.
- Tutor retention/deletion policy, LTI, OAuth, or live Canvas mutation.

## User flow

1. An authorized staff member runs the existing course Evaluation Protocol.
2. The service validates and hashes the committed benchmark dataset.
3. Required tutor retrieval, guard, support, and latency checks run offline.
4. A deterministic seed from the real course index is retrieved through the
   complete student-tutor path; an empty or non-retrievable course fails.
5. A failed required check makes the whole protocol fail.
6. The staff member can inspect case IDs and download the immutable report in
   JSON or Markdown as part of the course evidence pack.

## UX contract

- Keep the existing Evaluation Protocol surface and download flow.
- Check labels must explain the measured behaviour in plain language.
- Reports must separate measured metrics, thresholds, case failures, and known
  methodology limitations.
- No student identity, conversation history, model prompt, or source text is
  included in case diagnostics.

## Data and API

- No database migration: the protocol already stores JSON metrics and checks.
- Bump the immutable protocol version and record dataset filename + SHA-256.
- Record deterministic benchmark config and effective course-runtime retrieval
  config so a protocol cannot hide deployment drift.
- Preserve the existing Evaluation Protocol response schema and download URLs.
- Malformed cases, duplicate IDs, or missing expected labels produce an `error`
  protocol instead of a misleading partial pass.

## Security and privacy

- Dataset content is synthetic and committed; production content is never copied
  into the benchmark.
- Benchmark text is untrusted input and is never executed or interpolated into a
  system prompt.
- Runtime access remains course-scoped and non-disclosing.
- Only fixed metrics and thresholds affect pass/fail status.

## Acceptance criteria

- [x] A versioned synthetic dataset covers supported, unsupported, assessment,
  normal-help, and prompt-injection-shaped questions in Russian and English.
- [x] Retrieval benchmark reuses the complete production candidate scoring and
  selection adapter; the protocol records its version and fixed offline config.
- [x] Evaluation reports Recall@K, MRR, abstention accuracy, guard accuracy,
  labeled citation support, and offline p95 latency.
- [x] Required thresholds determine both CLI strict-mode and protocol status.
- [x] Dataset validation fails closed on malformed or duplicate cases.
- [x] Evaluation Protocol v2 stores dataset hash, thresholds, metrics, and
  redacted case-level diagnostics without changing the public schema.
- [x] Empty, hidden-only, or non-retrievable course content fails the required
  student-visible course-index readiness check.
- [x] A deployment threshold/provider configuration that makes runtime retrieval
  empty also fails course readiness and is recorded in protocol metrics.
- [x] Instructor/methodologist/admin can run; designer can only read; student
  receives a non-disclosing denial.
- [x] Focused tests, full backend suite, targeted pre-commit, and RAG/batch
  reviews pass.

## Test plan

- Unit tests for dataset validation, metrics, threshold failure, and redaction.
- Regression tests proving benchmark/runtime scoring and guard logic share the
  same production helpers.
- API authorization, persisted protocol, and download tests.
- Strict CLI success/failure tests and committed baseline generation.
- Full backend test suite and pre-commit gate.

## Batch review

Closed on 2026-07-14.

- General batch review: pass; no P0/P1 findings.
- RAG review initially found two P1 gaps: an empty course could pass readiness,
  and the course smoke hid deployment retrieval configuration drift. Both were
  fixed and covered by regression tests.
- Final targeted RAG recheck: no remaining P0/P1; the `.99/17` runtime-limit
  reproducer passes and fails protocol readiness as intended.
- Verification: 19 focused tests and 81 full backend tests passed; frontend lint
  and production build passed; strict benchmark CLI and targeted pre-commit
  passed.
- Deferred P2: the 18-case set is a synthetic regression sample, citation
  support is a labeled lexical proxy, offline p95 excludes database/model/network
  time, and provider-level quality/cost still needs an independent
  teacher-validated evaluation. Repo-wide pre-commit remains unverified because
  the existing dirty tree contains unrelated legacy files that its formatting
  hooks would mutate.
