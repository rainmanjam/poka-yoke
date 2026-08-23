## Workspace Deletion Design Plan
The goal is to prevent users from accidentally deleting their workspaces and then needing support to recover them.

## User Review Required
> [!WARNING]
> An "Are you sure?" modal is **not** recommended. According to the `ux` poka-yoke skill, "Are you sure?" asks about resolve, not facts. Users quickly develop click-through blindness to these modals and press "Confirm" reflexively. It acts as training, not a device, and fails to stop the mistake.

## Open Questions
> [!IMPORTANT]
> How should we redesign the workspace deletion flow? Please select one of the following alternatives:
> 
> 1. **(Recommended) Make it reversible (Soft Delete)**: The best approach (Control, Rung 1). Instead of fully deleting the workspace immediately, move it to a "trash" state with a 30-day retention period. Users can restore it themselves without contacting support. No confirmation dialog is needed.
> 2. **Type-to-Confirm (Warning, Rung 2)**: If soft-delete is too expensive to build right now, require the user to type the exact workspace name to confirm the deletion (e.g., "Type *my-workspace* to confirm"). This breaks the reflex loop and forces a conscious action proportional to the high consequence.
> 3. **Grace-Period Undo**: Delete immediately but show a toast with an "Undo" button for 5-10 seconds, delaying the actual backend deletion.

## Proposed Changes
Depending on your choice above, the implementation will involve:

### Choice 1: Soft Delete
#### [NEW] Backend soft-delete logic
#### [NEW] "Trash" UI for users to restore workspaces

### Choice 2: Type-to-Confirm
#### [MODIFY] Deletion Modal Component
- Change text from "Are you sure?" to "Delete workspace '[Name]' permanently?"
- Add a text input requiring the user to type the workspace name.
- Disable the "Delete" button until the input matches the workspace name exactly.

## Verification Plan
### Manual Verification
- Test the new flow to ensure accidental clicks do not result in permanent, unrecoverable data loss.
- For type-to-confirm, verify the submit button remains disabled until the exact text is matched.