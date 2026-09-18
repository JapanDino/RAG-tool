# UX03 Workshop workspace page

Status: complete

## User outcome

The product owner can inspect a complete, responsive workspace page in the
selected `Маршрут мастерской` direction before approving a production redesign.
The preview demonstrates navigation, a full hero, course selection, and the
selected-course action panel as one coherent experience.

## Users and permissions

- The route is a static local design-lab prototype.
- It makes no API request and changes no workspace permissions or Canvas data.

## Context and evidence

- `development/specs/done/UX02-workspace-hero-variants.md`
- The product owner explicitly preferred variant 02, `Маршрут мастерской`.
- `development/design/DESIGN_SYSTEM.md`
- `development/design/EXPERIENCE.md`

## Scope

- Add `/design-lab/workshop-workspace`.
- Show a complete administrator workspace shell using the selected visual
  direction.
- Include realistic static organization, navigation, hero, program/Canvas
  actions, two courses, course selection, evidence route, and current-course
  action.
- Keep the preview responsive and interactive only in local React state.

## Non-goals

- Applying the direction to `/workspace` before explicit approval.
- Loading real organization/course data.
- Redesigning tutor, audit, program, or Canvas pages in this batch.
- Introducing fonts, images, icon packages, or animation libraries.

## Design plan

Subject: a school administrator's working map. The page should feel like a
carefully assembled educational route on a studio table, not an enterprise
dashboard or a decorative children's pinboard.

Tokens:

- Route cobalt `#2457D6` — structure, active navigation, primary actions.
- Deep ink `#15315F` — typography and stable frame.
- Apricot marker `#FF9B73` — current position and human attention.
- Note yellow `#FFD95A` — guidance and provisional context.
- Workshop mint `#83D8C7` — supported connections and Canvas route.
- Grid paper `#F8FBFF` — neutral work surface.

Typography uses `Segoe UI Variable Display` for headings, `Segoe UI Variable
Text` for readable UI, and `Cascadia Mono` for route labels and indices.

Layout:

    +---------------------------------------------------------------+
    | brand / route status                         role switch       |
    +------------+--------------------------------------------------+
    | route nav  | HERO: copy + one full-width learning route       |
    |            +--------------------------------+-----------------+
    | org note   | assigned courses               | current course  |
    |            | selectable route cards         | exact action    |
    +------------+--------------------------------+-----------------+

Signature: one continuous dotted Course Route travels through the page and
changes meaning at labelled stations. Tape, rotation, and pin shapes are used
only at route anchors. The first decorative draft used a separate sticker on
every card; it was rejected as noisy and insufficiently product-like.

## User flow

1. Open the full-page preview and identify current role and organization.
2. Understand the hero and the two administrator destinations.
3. Select either synthetic course.
4. See the current course, role, Course Thread, and exact action update.
5. Return to the five-variant comparison if the page-level direction is not
   convincing.

## UX contract

- Desktop uses a stable sidebar, main workshop surface, and current-course rail.
- Mobile follows header, navigation, hero, courses, then current course.
- Course selection uses `aria-pressed`, controls an identified detail panel, and
  moves to it on mobile with reduced-motion support.
- All actual controls have visible focus and practical 44 px targets.
- Color is reinforced by labels, position, line style, and selected state.
- No horizontal page overflow at 390 px.

## Data and API

- Static synthetic data only.
- No data, API, schema, audit, or persistence changes.

## Security and privacy

- The preview contains no real user, school, course, model, or Canvas data.
- No fetch, localStorage, cookie, or credential access.

## Acceptance criteria

- [x] A complete workspace page visibly extends variant 02 beyond its hero.
- [x] Selecting a course updates the accessible current-course panel.
- [x] Desktop and 390 px mobile render without horizontal overflow.
- [x] Focus, selected state, touch targets, and reduced motion are supported.
- [x] Frontend lint and production build pass.

## Test plan

- frontend lint and production build;
- 1440 x 900 and 390 x 844 full-page screenshots;
- course-selection and mobile scroll check;
- overflow and console inspection;
- general and product/UX batch review.

## Batch review

- Frontend lint and production build passed.
- Desktop 1440 x 900 and mobile 390 x 844 full-page screenshots were inspected.
- Browser checks confirmed zero horizontal overflow, no console warnings or
  errors, accessible course selection, mobile detail movement, and the expected
  disabled prototype actions.
- General and product/UX reviews initially found focus contrast, a 43 px mobile
  brand target, and action-looking placeholders. The fixes added a dark focus
  outline with a yellow halo, a 44 px mobile target, and native disabled buttons
  with visible prototype explanation.
- Targeted reviewer rechecks reported no remaining P0/P1 findings.
