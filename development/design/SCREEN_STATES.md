# Screen-state checklist

UI work is incomplete until relevant states below are implemented and reviewed.

## Loading

- Explain what is loading when it may take more than a moment.
- Preserve stable layout to avoid disruptive movement.
- Show cancellable progress for long imports or audits when technically possible.

## Empty

- Distinguish “nothing created”, “nothing found”, and “no permission”.
- Provide one valid next action.
- Do not show an empty chart or table without explanation.

## Error

- State the failed operation.
- State whether user data or progress was preserved.
- Offer retry, correction, or support detail as appropriate.
- Keep provider stack traces and internal IDs out of ordinary UI.

## Permission denied

- Do not reveal whether an inaccessible resource exists.
- Explain which role or administrator can grant access.
- Keep navigation back to an allowed context.

## Insufficient evidence

- Say that course material does not support a reliable answer or finding.
- Show what sources were checked when safe.
- Offer a narrower question or teacher escalation.
- Do not manufacture an answer to avoid an empty response.

## Low confidence

- Explain the source of uncertainty.
- Keep the item reviewable.
- Avoid presenting a precise percentage without an actionable interpretation.

## Success

- Confirm the action using the same verb as the initiating control.
- Show the resulting object or next step.
- For drafts and change sets, state clearly that Canvas was not modified.

## Assessment guard

- Explain why a complete answer is restricted.
- Offer permitted help: clarification, first step, hint, concept review, or
  analogous practice problem.
