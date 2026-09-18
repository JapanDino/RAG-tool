# Canvas integration

## Product role

Canvas is an adapter and delivery surface, not the core domain model. Internal
users, memberships, courses, evidence, and review history must remain meaningful
without Canvas.

## Current implementation

The repository currently supports:

- manual base URL, course ID, and access-token import;
- course, module, page, assignment, quiz, outcome, and outcome-alignment reads;
- idempotent/version-aware persistence;
- teacher-authored alignment evaluation;
- read-only change-set generation.

Current URL validation requires HTTPS and blocks local/private addresses. This is
correct for arbitrary user-provided URLs but needs a safe deployment-specific
exception for the approved internal Canvas host.

## Verified Canvas Letovo usage evidence

A read-only browser observation with an authenticated learner account on
2026-07-19 established product-shape evidence, not an integration credential:

- the dashboard can contain dozens of published courses;
- one observed course used modules as an ordered route containing external
  links, Canvas pages, an assignment, and an attachment;
- another observed course used a syllabus-first home with learning goals,
  assessment tables, criteria/demo files, and calendar context;
- course structures therefore cannot be reduced to page and assignment counts.

The observation did not read grades, submissions, messages, or other users. It
did not verify the Canvas version, REST API access, teacher/admin UI, Developer
Key policy, or server topology. Browser cookies and authenticated HTML are never
an integration mechanism and must not be copied into the product or fixtures.

## Local test strategy

Use two complementary environments:

1. A lightweight Canvas Letovo interaction simulator owned by this repository.
   It reproduces only the navigation shell and LTI launch states needed for our
   product, uses synthetic course names/content, and provides deterministic
   link-heavy and syllabus-first fixtures.
2. A separate clean deployment of the official open-source Canvas LMS for LTI
   1.3, iframe, cookie, placement, and API conformance. It contains synthetic
   users and courses only and is not a clone of the school instance.

Do not scrape or mirror production Canvas HTML, copy its database or file store,
reuse session cookies, or reproduce private school content. Visual familiarity
comes from keeping Canvas chrome around an embedded LTI tool and using shared
course vocabulary, not from duplicating Canvas implementation or branding.

## First pilot contract

The first integration includes:

- LTI 1.3 Course Navigation launch;
- verified OIDC state, nonce, signature, issuer, audience, and deployment;
- internal user and course-membership mapping;
- correct student/instructor experience;
- scoped OAuth access to course content;
- automatic current-course selection;
- read-only synchronization that preserves syllabus and ordered module-item
  semantics, including external links and files;
- citations linking back to authorized Canvas resources;
- a course-navigation placement that stays inside Canvas for routine use;
- learner copy that contains no OAuth, scope, import, manifest, or RAG jargon;
- no grades, submissions, or course mutation.

## Deferred

- approved page/assignment write-back;
- LTI Deep Linking;
- Assignment and Grading Services;
- automated messages;
- student-submission analysis;
- Live Events.

## Access checklist

Before real integration, obtain:

- Canvas version and deployment topology;
- administrator contact;
- Developer Key and allowed scopes;
- LTI issuer, client ID, deployment ID, auth and JWKS endpoints;
- internal DNS name and TLS chain;
- test account for each role;
- one non-sensitive pilot course;
- organization retention and logging requirements.

## Safe write-back gate

Write-back is a later milestone and requires:

- visible before/after diff;
- exact target mapping;
- version or content-hash recheck;
- unpublished draft by default;
- one explicit teacher confirmation per operation;
- durable audit record;
- clear partial-failure handling.
