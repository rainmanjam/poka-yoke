## Goal Description
The goal is to prevent users from accidentally deleting their workspaces, which currently results in panicked emails to support. The initial proposal is to add an "are you sure?" modal before the delete action.

## User Review Required

> [!WARNING]
> I strongly advise **against** using a generic "are you sure?" modal as the primary fix.

Users quickly develop habituation or "click-through blindness" with frequent confirmation dialogs. They click "Confirm" with the same reflex as "OK", meaning the dialog protects no one while adding friction to every legitimate action. A dialog that asks "Are you sure?" questions the user's resolve, not the facts of the action.

Instead, I recommend we follow this explicit preference order for destructive actions (strongest first):

1. **Make it Reversible (Strongest Option)**: Implement a soft delete with a retention window (e.g., a 30-day trash/recycle bin). If a user makes a mistake, they can recover it themselves without contacting support. This is the best solution because it removes the permanent consequence entirely.
2. **Grace-Period Undo**: Perform the deletion immediately but show a "Workspace deleted. [Undo]" toast for several seconds. This offers a low-friction happy path while allowing full recovery from an accidental click (similar to Gmail's undo-send).
3. **Type-to-Confirm (For Irreversible Actions)**: If the deletion must remain irreversible, require the user to type the exact workspace name to confirm. This action is proportional to the consequence and cannot be done reflexively.
4. **Specific Consequence Dialog (Last Resort)**: If we absolutely must retain a standard dialog, it must state the exact workspace name and the scale of what is lost (e.g., "Delete 'Production' and its 42 projects permanently?"). 

> [!IMPORTANT]
> **Server-Side Enforcement**: The server must enforce the deletion rules, not just the UI. Hiding or gating the button in the UI is not enough; the backend API must be the ultimate authority on whether the deletion is permitted and how it is handled.

## Open Questions
- Do we have the backend capability to implement soft deletes (reversibility) for workspaces? This is the most effective way to eliminate support tickets for this issue.
- If soft deletes are not possible right now, would you prefer the "Grace-Period Undo" or the "Type-to-Confirm" approach?

## Proposed Changes
*Note: Since the codebase for the application itself wasn't specified, this is a conceptual outline.*

### Frontend
- Replace the immediate delete trigger with the chosen pattern (e.g., a type-to-confirm modal component or an undo-toast manager).
- Ensure the UI clearly communicates the consequences if the action is permanent.

### Backend
- Update the deletion endpoint to either mark the workspace as `deleted_at` (soft delete) or enforce the deletion securely.
- Ensure the server validates all conditions before proceeding, rather than trusting the client UI.

## Verification Plan

### Automated Tests
- Unit tests for the new UI component (e.g., verifying the type-to-confirm modal only enables the submit button on an exact match).
- Integration tests ensuring the backend properly soft-deletes or hard-deletes the workspace and enforces API-level authorization.

### Manual Verification
- Attempt to delete a workspace and verify the new UX flow prevents accidental clicks.
- If using soft delete, verify the workspace can be recovered.