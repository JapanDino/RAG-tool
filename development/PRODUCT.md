# Product contract

## Product thesis

The product is a local-first course intelligence platform. It builds a
verifiable representation of a course and turns that representation into
role-specific assistance for students, teachers, methodologists, program
designers, and administrators.

It is not a generic chatbot. Its answers and recommendations are constrained by
course evidence, permissions, and explicit human review.

## Core improvement loop

    Course content
      -> structured objectives, materials, and assessments
      -> student and teacher assistance
      -> evidence-backed feedback
      -> aggregated learning gaps
      -> teacher-approved course improvements
      -> measured change

## Primary users and outcomes

### Student

- Enter from the current Canvas course without selecting the course again or
  understanding OAuth, synchronization, retrieval, or model terminology.
- Recognize the exact course, its familiar module order, and the next useful
  action within one screen.
- Find and understand published course material.
- Receive explanations, hints, and self-check questions with citations.
- Get an explicit refusal when the course does not support an answer.
- Avoid accidental exposure to hidden content or complete graded solutions.

### Teacher

- Enter from the current Canvas course and continue with that exact course
  without repeating integration setup during normal use.
- Detect unsupported objectives, weak assessments, and Bloom mismatches.
- Review evidence and confidence before accepting a finding.
- Draft improvements without automatic publication.
- See aggregate unanswered and repeated student questions.

### Methodologist and program designer

- Trace program competencies through courses and assessments.
- Find gaps, duplication, prerequisite failures, and cognitive imbalance.
- Produce inspectable quality evidence instead of opaque scores.

### Administrator

- See aggregate course and program health.
- Monitor adoption, latency, cost, and improvement trends.
- Never use model output as an automatic personnel or disciplinary decision.

## Product principles

- Evidence before eloquence.
- Human approval before consequential writes.
- Role-specific assistance instead of one universal agent.
- Local processing and data minimization by default.
- Measured learning and time savings over message volume.
- Accessible, calm, user-facing interfaces rather than diagnostic dashboards.
- Preserve Canvas continuity: do not make people relearn the course structure,
  reselect a known course, or leave the Canvas frame for routine work.
- Use the user's vocabulary (`course`, `module`, `material`, `assignment`,
  `source`) and keep adapter, OAuth, RAG, scope, and provenance language in
  administrator or diagnostic surfaces only.

## Initial success metrics

- Citation integrity and unsupported-question refusal rate.
- Teacher acceptance and edit distance of findings and drafts.
- Time saved during course audit and course revision.
- Student helpfulness and time-to-supported-answer.
- Repeated-question and unresolved-topic trends.
- Inference latency and cost per active course or learner.
- Time from an LTI launch to the first useful action and completion rate for
  three basic tasks: find the next material, open its source, and ask for help.

## Non-goals for the first Canvas pilot

- Autonomous grading.
- Reading student submissions by default.
- Automatic publication or mutation of a live course.
- Psychological or ability profiling.
- Cross-course access without explicit membership.
- A single numeric ranking of teachers or students.
