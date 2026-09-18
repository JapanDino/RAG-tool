# UX01 Expressive workspace redesign

Status: complete

## User outcome

Students, teachers, methodologists, program designers, and administrators open a
workspace that feels like a living map of learning instead of a sparse
engineering dashboard. The existing role, course, and Canvas workflows remain
immediately understandable while the product gains a recognisable visual voice.

## Users and permissions

- All existing workspace roles may see the redesigned shell and their existing
  role-specific navigation.
- Organization administrators may use the redesigned Canvas registration page.
- The redesign does not add permissions, data access, or Canvas mutations.

## Context and evidence

- `development/design/DESIGN_SYSTEM.md`
- `development/design/EXPERIENCE.md`
- `development/design/SCREEN_STATES.md`
- `frontend/pages/workspace.tsx`
- `frontend/pages/workspace/integrations/lti.tsx`
- The current desktop and mobile screenshots are legible but visually read as a
  sparse grid-led dashboard. The user explicitly asked for a more attractive,
  less minimal experience.

## Scope

- Establish one expressive visual system for `/workspace` and
  `/workspace/integrations/lti`.
- Reshape the workspace hero, navigation, course list, selected-course panel,
  Canvas hero, connection route, content panels, registration cards, and form.
- Preserve all existing data loading, actions, labels, focus behavior, and safe
  failure states.
- Use CSS-native illustration so the interface works offline and has no new
  asset or font dependency.

## Non-goals

- Redesigning every course, tutor, audit, and program subpage in this batch.
- Changing API contracts, authorization, storage, LTI behavior, or Canvas data.
- Introducing an external font, icon library, animation library, or framework
  migration.

## Visual direction

Subject: a living educational atlas for a school community. Audience: students
and school staff who need clarity without an enterprise-control-room mood.

### Tokens

- Deep atlas `#101936` — text and structural depth.
- Learning indigo `#5865F2` — primary action and active paths.
- Lagoon `#15A99B` — supported and connected states.
- Warm coral `#F47B69` — human attention and visual counterpoint.
- Sun note `#F3C85B` — guidance and provisional steps.
- Mist paper `#EEF3FF` — atmospheric application background.

Typography uses `Segoe UI Variable Display` or `Manrope`-compatible system
fallbacks for expressive headings, `Segoe UI Variable Text`/`Source Sans 3`
fallbacks for body copy, and `IBM Plex Mono`/`Cascadia Mono` only for technical
identifiers.

### Layout sketches

Desktop workspace:

    +---------------------------------------------------------------+
    | brand + role                                  identity control |
    +----------+--------------------------------+-------------------+
    | role nav | statement + actions            | COURSE ORBIT      |
    |          |                                | objective---task  |
    |          +--------------------------------+-------------------+
    |          | course route / course cards    | selected course   |
    +----------+--------------------------------+-------------------+

Mobile workspace:

    +-----------------------+
    | brand / role picker   |
    | compact role nav      |
    | statement             |
    | COURSE ORBIT          |
    | course cards          |
    | selected course       |
    +-----------------------+

Canvas route:

    +---------------------------------------------------------------+
    | CONNECT CANVAS: statement          animated connection orbit   |
    +---------------------------------------------------------------+
    | address ==== key ==== registration ---- first launch           |
    +--------------------------------------+------------------------+
    | registration package                | next exact action      |
    +--------------------------------------+------------------------+
    | registrations / form                                          |
    +---------------------------------------------------------------+

Signature: the Course Thread becomes a spatial learning orbit. It visibly links
recognisable educational objects and changes shape between the workspace and
the Canvas connection route. It remains functional, labelled, and restrained;
decorative gradients and unrelated illustrations are excluded.

## User flow

1. Open the workspace and immediately recognise the current role and primary
   task.
2. Scan the learning orbit, select a course, and see the exact available action.
3. If an administrator, open the Canvas route and follow its ordered stations.
4. Complete the same existing action with clearer visual confirmation.

## UX contract

- The hero is the page thesis; secondary navigation never competes with it.
- The Course Thread/orbit is the only deliberately bold visual device.
- Desktop uses an asymmetric composition; mobile follows the same reading order
  without horizontal scrolling.
- Loading, empty, error, permission, draft, active, blocked, and success states
  retain explicit text and actions.
- Primary action labels remain unchanged so the initiating action and result use
  the same vocabulary.
- All controls require visible focus, 44 px practical touch targets, readable
  contrast, and non-color status cues.
- Ambient motion is limited to the orbit and disabled by
  `prefers-reduced-motion`.

## Data and API

- No schema, migration, endpoint, request, response, or versioning changes.
- Existing audit and authorization behavior remains unchanged.

## Security and privacy

- Existing untrusted content remains rendered as text.
- The redesign exposes no new course, identity, model, credential, or Canvas
  data.
- Permission denials remain non-disclosing.

## Acceptance criteria

- [x] `/workspace` and the Canvas registration route share the new visual system
  and no longer read as sparse engineering dashboards.
- [x] Existing role switching, course selection, navigation, copy, refresh,
  registration, edit, confirmation, and cancellation actions still work.
- [x] Desktop and 390 px mobile layouts have no horizontal page overflow.
- [x] Keyboard focus and reduced-motion behavior are visible and usable.
- [x] Loading, empty, error, permission, draft, active, and success states remain
  understandable without relying on color.
- [x] Frontend lint and production build pass.

## Test plan

- frontend lint and production build;
- desktop and 390 px screenshots for both routes;
- console and horizontal-overflow inspection;
- keyboard traversal and visible focus;
- reduced-motion inspection;
- targeted general quality and product-UX review at batch close.

## Batch review

General quality and product/UX reviews completed after one targeted fix pass.
No P0/P1 findings remain. The fixes added selected-course semantics and honest
action copy, mobile guidance and action-panel scrolling, visible focus for raw
configuration, reliable copy announcements, and practical 44 px targets.

The new system intentionally covers the product entry point and Canvas route in
this batch. Course, tutor, audit, and program subpages remain a follow-up visual
migration so behavior and review scope stay bounded.
