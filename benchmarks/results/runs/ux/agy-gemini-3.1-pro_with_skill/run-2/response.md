## Goal Description
The goal is to prevent users from accidentally deleting their workspaces. The current proposal is to add an "Are you sure?" confirmation modal before the delete action.

## User Review Required

> [!WARNING]
> An "Are you sure?" modal is highly susceptible to **click-through blindness**. Users see these dialogs so often that they dismiss them reflexively without reading, which means it won't actually stop the accidental deletions you are seeing. It asks about user resolve, not facts.

Based on the `poka-yoke` UI guidelines, we should reach for a higher-rung device. Here is the strict preference order for destructive actions like deleting a workspace:

1. **Make it reversible (Control - Rung 1)**
   Instead of hard-deleting immediately, implement a soft-delete (a trash/recycle bin with a retention period, e.g., 30 days). The mistake has no permanent consequence and needs no UI gate at all. *This is the strongest solution but requires backend changes.*
2. **Grace-period undo (Control - Rung 1)**
   Perform the action but hold the effect for several seconds (e.g., 5-10s), showing a toast: "Workspace deleted. [Undo]". There is no friction on the happy path, and full recovery on the mistaken one.
3. **Type-to-confirm (Warning - Rung 2)**
   If it must be an irreversible, immediate delete, require an action proportional to the blast radius. A modal that asks the user to type the exact workspace name (e.g., `production-api`) to enable the "Delete forever" button.
4. **Specific consequence dialog (Warning - Rung 2)**
   If you must use a standard modal, it must name the object and consequence exactly, not "Are you sure?". Example: "Delete workspace 'production-api' permanently? This will destroy 1,204 files." The button must be labeled "Delete forever", not "OK".

## Open Questions

> [!IMPORTANT]
> 1. Is soft-delete (a trash bin with a 30-day retention) feasible on the backend?
> 2. If not, would you prefer a **grace-period undo toast** (frictionless) or a **type-to-confirm modal** (high friction, appropriate for catastrophic actions)?

## Proposed Changes
*Depending on the chosen approach, the UI implementation will change.*

### Approach A: Type-to-Confirm (If immediate delete is required)
#### [MODIFY] Workspace Delete Flow
- Remove the "Are you sure?" text.
- Add a text input requiring the exact workspace name to be typed.
- Disable the "Delete" button until the input matches the workspace name.
- Change the button text to "Delete workspace".

### Approach B: Grace-Period Undo (If slight delay is acceptable)
#### [MODIFY] Workspace Delete Flow
- Remove confirmation modal entirely.
- On click, hide the workspace immediately and show a toast "Workspace [Name] deleted. [Undo]".
- Delay the actual API call by 5-10 seconds. If Undo is clicked, cancel the API call and restore the UI.

## Verification Plan
### Manual Verification
- Attempt to delete a workspace and verify the new protective device works as intended.
- Verify that accidental clicks can be easily recovered from (or are structurally prevented).