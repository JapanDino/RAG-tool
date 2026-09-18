# B09 Research protocol freeze

Status: done

## User outcome

A researcher or authorized school reviewer can inspect and reproduce one frozen
study protocol for evaluating the role-aware Canvas agent before any real pilot
outcomes are inspected. The export clearly separates synthetic engineering
baselines from future teacher-validated and participant evidence.

## Users and permissions

- Research owner and approved methodology reviewer: inspect the committed
  protocol, verify its digest, and generate deterministic JSON/Markdown exports.
- School ethics/administration reviewers: inspect the privacy, consent, opt-out,
  retention, exclusion, and adverse-event gates before approving collection.
- Product users, students, teachers, and Canvas accounts: no new application
  route, data collection, assignment, condition, or research flag in B09.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B09.
- `development/PRODUCT.md`: evidence, human review, learning/time outcomes, and
  no teacher/student surveillance.
- `development/agents/research-methodology-reviewer.md`.
- `development/agents/rag-evaluator.md`.
- `docs/BASELINE_QUALITY_REPORT.md` and `docs/TEST_PROGRAM.md`: current bundled
  data is curated/synthetic regression evidence, not classroom proof.
- Completed B02-B07/B10 offline agent foundation and signed Canvas simulator.

## Scope

- Add a versioned machine-readable preregistration for “Teacher-Calibrated
  Multilingual RAG for Auditing Constructive Alignment in LMS Courses”.
- Freeze the research question, directional hypotheses, estimands, primary and
  secondary endpoints, baselines, exclusions, missing-data handling,
  multiplicity policy, analysis plan, course-level RU/EN split policy, and
  stopping rules.
- Record exact product workflow, retrieval, policy, prompt/model, dataset, and
  code-version slots required for a reproducible run.
- Add a strict local validator and deterministic JSON/Markdown exporter that
  records the canonical protocol SHA-256 and refuses an analysis-ready claim
  while real datasets, approvals, or required version pins are absent.
- Commit only protocol metadata and synthetic dataset identities/hashes; never
  participant data, course text, labels, prompts, answers, or credentials.

## Non-goals

- No participant recruitment, randomization, intervention, pilot execution,
  classroom effectiveness claim, model tuning, literature-novelty claim, or
  inspection of real outcomes.
- No Canvas, LTI, course, model-host, database, policy, agent-run, or UI change.
- No publication-ready power claim based on the bundled synthetic sets.
- No student study before institutional approval and consent/assent; any study
  involving minors requires a separate approved amendment.

## User flow

1. The research owner edits the protocol only before confirmatory data access.
2. The validator checks closed fields, unique IDs, course-level split rules,
   baseline isolation, metrics, analysis, approvals, and required version pins.
3. The exporter canonicalizes the protocol, verifies referenced synthetic file
   hashes, and writes deterministic JSON and reviewer-readable Markdown.
4. The report states `frozen_awaiting_approvals_and_data` until all external
   gates and real split manifests exist; it cannot silently report readiness.
   B09 has no metadata-only override: trusted approval verification and real
   dataset ingestion belong to a later approved execution batch.

## UX contract

- Markdown starts with claim status, frozen question, compared conditions, and
  “what this protocol can/cannot prove”.
- Primary endpoints, analysis populations, exclusions, missing data, ethics,
  version pins, and dataset classes are visually separate and plain-language.
- Missing approvals/data/version pins appear as explicit blockers, never hidden
  warnings or an optimistic score.
- Output is readable in a terminal/GitHub at narrow widths; no web UI is added.

## Data and API

- No database migration or HTTP endpoint.
- `research/protocols/*.json` is the source contract; a schema version and
  immutable protocol ID are required.
- The canonical digest excludes generated timestamps and output paths.
- Dataset entries distinguish `synthetic_regression`, `teacher_validated`, and
  `participant_outcomes`; real entries contain opaque IDs/hashes only.
- Export overwrites only explicitly requested local output files and never
  changes the source protocol.

## Security and privacy

- Protocol validation rejects direct identifiers, free-form participant/course
  content, credentials, URLs with embedded secrets, and unknown fields.
- Course split is the unit of isolation; no course may occur in more than one of
  train/development/test, and final test labels cannot be used for tuning.
- Student/teacher outcomes require approval, consent/assent as applicable,
  data minimization, opt-out, retention, access, deletion, and adverse-event
  rules before collection.
- A locally authored JSON file can never authorize collection or turn
  `analysis_ready` on; later execution must verify trusted approvals and actual
  dataset/split artifacts rather than self-declared hashes or counts.
- Aggregated product metrics do not become personnel/student rankings, and
  message volume is not a learning endpoint.

## Acceptance criteria

- [x] The protocol freezes one research question, hypotheses, estimands,
  endpoints, baselines, exclusions, missing-data, multiplicity, and analysis.
- [x] RU/EN datasets use course-level split isolation and distinguish synthetic
  engineering baselines from future confirmatory evidence.
- [x] Required versions, dataset hashes, latency/tokens/cost/failure fields, and
  deterministic protocol SHA-256 make a run reproducible.
- [x] Validation rejects course leakage, duplicate IDs, unknown fields, unsafe
  identifiers/content, tuning on test, absent standard-RAG/non-agent baselines,
  and unsupported classroom-effectiveness claims.
- [x] Ethics gates fail closed before participant collection, especially for
  minors, while absent real data remains an explicit external blocker.
- [x] JSON and Markdown exports are deterministic, privacy-safe, and state what
  the protocol can and cannot prove.
- [x] Focused/full tests, pre-commit, `git diff --check`, and research/RAG/
  agent-safety/batch reviews have no open P0/P1.

## Test plan

- Unit: canonical digest, closed-schema parsing, condition/endpoint contracts,
  split isolation, hash verification, blocker derivation, and secret/PII guards.
- CLI: deterministic JSON/Markdown generation, strict failure on malformed
  protocol/reference hash, and source immutability.
- Regression: bundled synthetic datasets remain labeled as non-confirmatory;
  no product/Canvas/model/database mutation or network call.
- Batch: full pytest, frontend lint/build, repo-wide pre-commit, and
  `git diff --check`; no browser run because B09 adds no web surface.

## Batch review

Research-methodology, RAG, agent-safety, and general quality reviews passed
after all P0/P1 findings were corrected. Final checks: 21 focused tests, 485
full backend tests, pre-commit, frontend lint/build, and `git diff --check`.
