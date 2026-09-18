# Design system contract

This is the canonical Workshop Route design contract. New product UI extends
this language by default; deviations require a feature-specific reason and
must still preserve the shared tokens, interaction states, and Course Route
semantics.

## Visual character

- Clear, tactile, optimistic, and educational.
- A working map assembled from grid paper, evidence notes, and route markers.
- High information clarity without enterprise-dashboard density or childish decoration.
- Quiet paper surfaces carry most of the interface.
- Color encodes route position, evidence, and review state.
- The Course Route is the single expressive visual device.

## Initial palette

| Token | Value | Role |
| --- | --- | --- |
| Workshop ink | `#15315F` | Primary text and strong structure |
| Slate | `#5A6F8A` | Secondary text |
| Grid paper | `#F8FBFF` | Application background and route surface |
| Paper | `#FFFFFF` | Primary work surfaces |
| Warm paper | `#FFF9E9` | Guidance and side notes |
| Route cobalt | `#2457D6` | Navigation and primary action |
| Evidence mint | `#83D8C7` | Supported evidence and connected state |
| Marker apricot | `#FF9B73` | Current position and human attention |
| Note yellow | `#FFD95A` | Uncertainty and review attention |
| Risk red | `#B94952` | Errors and high-risk gaps |

Do not use color as the only status signal. Every state also needs text, shape,
or iconography with an accessible name.

## Typography direction

- Display and navigation: `Segoe UI Variable Display`, then `Segoe UI`.
- Body and UI: `Segoe UI Variable Text`, then `Segoe UI`.
- Route labels and technical identifiers only: `Cascadia Mono`, then a system
  monospace fallback.

Do not load external fonts in production. The chosen system stack has Cyrillic
coverage and makes the locally hosted product independent of third-party font
requests.

## Type and spacing

- Base body size: 16 px minimum.
- Dense data may use 14 px with sufficient line height.
- Use a 4 px spacing base with a restrained scale: 4, 8, 12, 16, 24, 32, 48.
- Prefer alignment and whitespace over nested cards. Use offset apricot shadows,
  tape, and rotation only for current or provisional objects.
- Limit long reading lines to approximately 65–75 characters.

## Component foundation

Start with no more than these shared components:

- Button;
- Link;
- TextField/TextArea;
- Select;
- Tabs;
- Dialog;
- StatusBadge;
- SourceCitation;
- ConfidenceNotice;
- EmptyState;
- CourseThread;
- Toast/InlineNotice.

Build role-specific composites from these. Do not introduce Storybook until the
shared component surface becomes costly to inspect in product screens.

## Required states

Every interactive component must define:

- default;
- hover where applicable;
- visible keyboard focus;
- disabled;
- busy;
- error;
- selected/pressed where applicable.

## Responsive baseline

- Desktop reference: 1440 × 900.
- Mobile reference: 390 × 844.
- No critical action may require hover.
- Evidence panels must remain readable without horizontal page scrolling.
