# UX04 Workshop product migration

Status: complete

## User outcome

Every production-facing route feels like one coherent product based on the
approved `Workshop Route` direction. Students, teachers, methodologists,
program designers, and administrators keep their existing workflows while
learning one visual language across the product.

## Users and permissions

- All existing roles and permission boundaries remain unchanged.
- The batch changes presentation and shared UI primitives only.
- No Canvas, course, tutor, identity, or program write is added.

## Context and evidence

- `development/specs/done/UX03-workshop-workspace-page.md`
- The product owner explicitly approved the full-page Workshop direction and
  asked to apply it to the whole product and future work.
- `development/design/DESIGN_SYSTEM.md`
- `development/design/EXPERIENCE.md`
- `development/design/SCREEN_STATES.md`

## Scope

- Make Workshop Route the canonical design direction in product documentation.
- Add shared production tokens and Course Route primitives.
- Migrate `/workspace` and `/workspace/integrations/lti`.
- Migrate teacher and student course pages.
- Migrate program map and program overview pages.
- Bring the legacy root surface into the same token and surface language.
- Preserve responsive, keyboard, loading, empty, error, permission,
  low-confidence, and disabled states.

## Non-goals

- Changing data fetching, APIs, schemas, permissions, or Canvas behavior.
- Replacing the Pages Router or splitting the existing large feature files.
- Adding external fonts, image packages, or animation libraries.
- Making every panel look like a paper note; the route is the signature and
  operational content stays quiet.

## Design contract

Subject: an evidence-backed educational route assembled on a school workshop
table. The route is purposeful: objectives, material, evidence, review, and
approved change are stations rather than decorative dots.

Tokens:

- Workshop ink `#15315F` for stable structure and text.
- Route cobalt `#2457D6` for navigation and primary actions.
- Apricot marker `#FF9B73` for the current position and human attention.
- Note yellow `#FFD95A` for provisional guidance and review.
- Evidence mint `#83D8C7` for supported connections.
- Grid paper `#F8FBFF` and warm paper `#FFF9E9` for working surfaces.

Typography uses system-available `Segoe UI Variable Display` for restrained
headings, `Segoe UI Variable Text` for UI, and `Cascadia Mono` for route labels
and technical identifiers. No network font request is permitted.

Signature: the Course Route appears only where it communicates a real sequence
or evidence relationship. Tape, rotation, and offset shadows mark current or
provisional objects; ordinary forms and dense review lists remain straight.

## User flows

1. Enter the role-aware workspace and identify the current route.
2. Continue to a course, tutor, program, or Canvas installation task.
3. Recognize the same navigation, action hierarchy, evidence language, and
   state treatment on the destination page.
4. Complete the existing task without learning a page-specific visual system.

## Acceptance criteria

- [x] Design documentation establishes Workshop Route as the default for future UI.
- [x] All production routes use the canonical palette, typography, surfaces,
  buttons, and focus treatment.
- [x] Course Route remains meaningful and does not become repeated decoration.
- [x] Existing behaviors, API contracts, and permission boundaries are unchanged.
- [x] Desktop and 390 px mobile layouts have no horizontal page overflow.
- [x] Relevant loading, empty, error, permission, disabled, and selected states remain legible.
- [x] Frontend lint and production build pass.

## Test plan

- frontend lint and production build;
- production route inventory and CSS hardcoded-color audit;
- desktop and 390 px mobile screenshots for each reachable route/state;
- keyboard focus, overflow, console, disabled, and selected-state checks;
- general and product/UX batch review.

## Batch review

- The canonical design documentation, agent rule, global tokens, production
  wrapper, and route-specific palettes were inspected.
- Frontend lint and production build passed after the final fixes.
- Desktop and 390 px browser checks covered the root laboratory, workspace,
  Canvas permission, tutor permission, program permission, and program overview
  permission routes. All final checks reported zero horizontal overflow.
- Playwright verified the compact mobile workspace and settings controls, the
  localized workspace transport alert, collapsed developer tools, selected
  Workshop design marker, and protected-name behavior.
- Initial reviews found two product P1s (raw transport copy and split footer
  identity) plus one quality P1 (hidden mobile workspace/settings controls).
  The fixes localized errors with preservation/retry guidance, consolidated
  the footer under Kontur, collapsed developer links, and retained compact
  44+ px mobile controls.
- General and product/UX targeted rechecks reported no remaining P0/P1 findings.
