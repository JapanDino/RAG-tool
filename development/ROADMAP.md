# Roadmap

The roadmap is outcome-oriented. Detailed tasks belong in active specs.

## M00 — Baseline and development control

Outcome: current course-audit functionality has a verified baseline and one
canonical technical workspace.

Gate:

- technical directory and agent guide exist;
- current tests and build commands are documented;
- secrets are removed from agent configuration;
- current working tree is intentionally committed or separated.

## M01 — Identity and roles

Outcome: users can access only the organizations, courses, and role-specific
actions assigned to them.

Gate:

- organization, user, and membership model;
- backend permission checks;
- local development login;
- student, instructor, methodologist, designer, and administrator roles;
- authorization tests.

## M02 — Teacher workspace

Outcome: a teacher can import, audit, review, compare, and improve a course in a
coherent workflow.

Gate:

- role-specific teacher shell;
- evidence-first findings;
- accepted/rejected review flow;
- version comparison;
- draft change package;
- measured audit duration and acceptance.

## M03 — Grounded student tutor

Outcome: a student can receive cited explanations and hints without exposure to
hidden content or unrestricted assessment answers.

Gate:

- student-specific policy and prompt;
- published-content boundary;
- assessment guard;
- conversation and feedback history;
- refusal and citation evaluation;
- teacher-configurable tutor rules.

## M04 — Program intelligence

Outcome: methodologists and program designers can inspect competency coverage,
duplication, prerequisites, and assessment progression across courses.

Gate:

- program and competency entities;
- course contribution mapping;
- program-level audit;
- evidence drill-down;
- aggregate administration view.

## M05 — Canvas read-only pilot

Outcome: a Canvas Letovo learner or teacher opens the product inside the Canvas
course interface, immediately recognizes the exact course and its familiar
structure, and reaches a useful role-specific action without integration jargon
or repeated setup.

Gate:

- LTI 1.3 launch;
- identity and role mapping;
- scoped OAuth access;
- automatic course context;
- a local Canvas Letovo interaction simulator with synthetic link-heavy and
  syllabus-first courses for fast UI and signed-launch tests;
- a separate clean self-hosted Canvas LMS instance for real LTI/iframe contract
  checks without copying the school database, files, credentials, or users;
- read-only synchronization that preserves syllabus, module and item order,
  item type, pages, assignments, files, and external-link provenance;
- Canvas-native course entry: exact course name, `Продолжить по курсу`,
  `Спросить по материалам`, and a familiar ordered course map;
- no student-facing OAuth, scope, import, RAG, manifest, or synchronization UI;
- teacher connection and intake controls remain separate from the learner flow;
- internal TLS and explicit private-host allow-list;
- teacher and student pilot flows validated with role-specific test accounts;
- desktop and 390 px iframe checks plus task-based usability review.

Sequence:

1. Build the lightweight simulator and normalized Letovo course-topology
   contract from synthetic data.
2. Deliver the learner current-course entry flow inside the simulated Canvas
   frame.
3. Run the same LTI launch and iframe flow against a clean self-hosted Canvas.
4. Validate teacher and administrator surfaces only after role-specific test
   accounts and approved non-sensitive pilot content exist.
5. Connect the school instance only through an approved Developer Key, exact
   host/TLS policy, and production credential custody.

## M05A — Role-aware Canvas agent foundation

Outcome: one assistant entry point inside the current Canvas course coordinates
bounded, typed, permission-checked tools for the exact learner or instructor
without exposing internal RAG, provider, or integration mechanics.

Gate:

- central ModelGateway for approved OpenAI-compatible agent-host models;
- server-derived agent context from the exact LTI product session;
- closed role/workflow/tool policy with execution-time authorization;
- evidence and citation validation outside the model;
- bounded steps, time, tokens, cost, retries, and deterministic fallback;
- learner explanation, hint, self-check, source, and abstention workflows;
- instructor audit, evidence, draft, review, and change-preview workflows;
- prompt/tool-output injection, provider-failure, and role-isolation evaluation;
- desktop/mobile/accessibility task flows inside the Canvas frame.

## M05B — Closed-loop course improvement

Outcome: privacy-safe aggregate learner difficulties become evidence-backed,
teacher-reviewable course-improvement candidates without exposing transcripts or
turning the system into student or teacher surveillance.

Gate:

- minimum-cohort aggregate learning-gap signals;
- no individual transcript or learner ranking in teacher/admin projections;
- cited intervention drafts linked to explicit reviewer decisions;
- acceptance, edit distance, time-to-decision, and course-version comparison;
- program/methodologist tools built from the existing competency evidence;
- aggregate operational administration tools for adoption, latency, cost,
  retention, and integration health;
- end-to-end question -> aggregate -> draft -> review evaluation.

## M05C — Research-ready evaluation

Outcome: the system can support a reproducible study of role-aware,
evidence-constrained LMS agents instead of presenting synthetic demos as
research results.

Gate:

- frozen hypotheses, baselines, primary endpoints, and analysis plan;
- Canvas/search, standard-RAG, and bounded-agent comparison;
- held-out Russian/English course splits with dataset hashes;
- correctness, citation entailment, leakage, calibration, abstention, learning,
  teacher-time, latency, and cost metrics;
- reproducible model, prompt, workflow, retrieval, and policy versions;
- institutional approval, consent/assent, minimization, opt-out, and retention
  before any student study;
- independent RAG, safety, and research-methodology review.

Detailed execution order, component contracts, estimates, and reviewer routing
are defined in `development/AI_CANVAS_AGENT_PLAN.md`.

## M06 — Approved Canvas write-back

Outcome: a teacher can apply an individually approved, version-checked draft to
Canvas with an audit trail.

Gate:

- visible diff;
- optimistic concurrency/version check;
- unpublished draft by default;
- explicit confirmation;
- durable operation log;
- recovery or compensating action.
