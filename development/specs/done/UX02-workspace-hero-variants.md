# UX02 Workspace hero variants

Status: complete

## User outcome

The product owner can compare five genuinely different visual directions for the
same workspace hero, select one on a single page, and use that choice to guide
the next product-wide visual migration.

## Users and permissions

- This is a local design-lab route for product/design review.
- It reads no user or course data and changes no product permissions.

## Context and evidence

- `development/design/DESIGN_SYSTEM.md`
- `development/design/EXPERIENCE.md`
- `development/specs/done/UX01-expressive-workspace-redesign.md`
- The same administrator hero content is used in every preview so the choice is
  about visual structure, not different copy or capabilities.

## Scope

- Add `/design-lab/workspace-hero-variants`.
- Render five responsive versions of one hero block on the same neutral review
  page.
- Provide a clear local selection control and selected-state summary.
- Keep the comparison entirely frontend-only and CSS-native.

## Non-goals

- Applying a variant to production routes before the user chooses.
- Changing workspace behavior, APIs, permissions, or Canvas integration.
- Treating palette swaps as separate concepts.

## Shared content contract

Every concept contains exactly the same user-facing information:

- context: `Контур организации`;
- heading: `Доступы и качество — в разных слоях`;
- description about separating assignments from learning analytics;
- actions: `Открыть обзор программ` and `Подключить Canvas`;
- role: `Администратор`;
- relationship: `Цель — Материал — Проверка`.

## Design plan

Shared neutral review tokens: Ink `#101936`, Paper `#FFFFFF`, Mist `#EEF3FF`,
Slate `#5B6781`. Display role uses `Segoe UI Variable Display`; body uses
`Segoe UI Variable Text`; utility labels use `Cascadia Mono` fallbacks.

Concept accents and signatures:

1. Orbital atlas — Indigo `#5865F2`, Lagoon `#15A99B`, Coral `#F47B69`, Sun
   `#F3C85B`. Signature: role-centered learning orbit.
2. Workshop route — Cobalt `#2457D6`, Apricot `#FF9B73`, Note `#FFD95A`, Mint
   `#83D8C7`. Signature: a tactile pinned route crossing the work surface.
3. Program layers — Aubergine `#452B63`, Iris `#8367D8`, Aqua `#53C7BE`, Lime
   `#B9D96B`. Signature: translucent curriculum strata with a vertical trace.
4. Learning portal — Night `#090E24`, Electric `#7C6CFF`, Cyan `#31D4C5`, Ember
   `#FF806F`. Signature: one luminous arched gateway carrying the Course Thread.
5. Folded map — Marine `#163D6B`, Sky `#63A9FF`, Orange `#FF8A4C`, Ice
   `#E7F6FF`. Signature: a geometric fold that turns the hero into a route sheet.

Layout sketches:

    1 ORBIT          2 WORKSHOP       3 LAYERS
    +copy---(map)+   +route----------+ +copy|layer|+
    |actions role|   |copy   notes   | |act |role |
    +-------------+  +---------------+ +----------+

    4 PORTAL         5 FOLDED MAP
    +copy | arch  +  +label/copy----+
    |acts | route +  |----fold/map--|
    +-------------+  +actions-------+

The first brainstorm included a standard card/bento comparison and five palette
skins. Both were rejected before implementation: they could fit any admin
product and would not test how the Course Thread expresses this educational
product. Each retained direction therefore changes spatial logic and gives the
learning relationship one concept-specific role.

## User flow

1. Open the comparison route.
2. Read the fixed shared-content notice.
3. Review all five concepts at the same viewport and content density.
4. Choose `Выбрать этот вариант` on one concept.
5. See the selected concept confirmed in the sticky comparison header.

## UX contract

- The comparison chrome stays visually neutral and never competes with previews.
- Each concept has one bold signature and otherwise disciplined structure.
- Concepts remain distinguishable without relying on color alone.
- 390 px mobile preserves the same content and selection control without page
  overflow.
- Selection uses native radio semantics, visible focus, and a text confirmation.
- Motion is optional ambient emphasis and stops under reduced motion.

## Data and API

- No data, schema, API, persistence, or audit changes.
- Selection lasts only for the mounted local page.

## Security and privacy

- The route uses static synthetic content only.
- No identity, organization, course, model, or Canvas request is made.

## Acceptance criteria

- [x] Five visually and structurally distinct versions render with identical
  content.
- [x] A reviewer can select exactly one version and see a text confirmation.
- [x] The route works at 1440 x 900 and 390 x 844 without horizontal overflow.
- [x] Keyboard focus, radio semantics, and reduced-motion handling are present.
- [x] Frontend lint and production build pass.

## Test plan

- frontend lint and production build;
- full-page desktop and mobile screenshots;
- page overflow and browser console inspection;
- keyboard selection check;
- general and product/UX batch review.

## Batch review

General quality and product/UX reviews passed after one targeted fix pass. No
P0/P1 findings remain. Fixes added a compact sticky selection confirmation,
unique accessible radio names, and genuinely different macro compositions for
the full-width Workshop route and centered Portal scene.

The design lab is complete, but no concept has been applied to production. The
product owner still needs to choose a direction.
