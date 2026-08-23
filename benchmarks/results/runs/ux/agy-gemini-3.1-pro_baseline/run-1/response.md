## Goal Description
Prevent users from accidentally deleting their workspaces. The current proposal is to add an "Are you sure?" modal, but as per the poka-yoke `ux` principles, this is a **Rung 0** (ineffective) device because users quickly develop click-through blindness and click "Yes" reflexively. It tests resolve rather than facts.

Instead, we need to implement a true poka-yoke device.

## User Review Required
> [!IMPORTANT]
> The "Are you sure?" modal is strongly discouraged. We need to choose one of the following true poka-yoke devices. Please let me know which approach you prefer for your application:

**Option 1: Soft Delete (Rung 1 - Control) — Recommended**
Instead of permanently deleting the workspace immediately, move it to a "Trash" state with a 30-day retention period. 
* **Pros**: Mistakes have no permanent consequence and need no UI gate at all. This is the ultimate poka-yoke.
* **Cons**: Requires backend changes to support soft deletion and a retention worker.

**Option 2: Type-to-Confirm (Rung 2 - Warning)**
Require the user to type the exact workspace name to confirm the deletion.
* **Pros**: Cannot be done reflexively. Action is proportional to the consequence (high blast radius).
* **Cons**: Adds friction. Should only be used if the action is genuinely irreversible.

**Option 3: Specific Consequence Dialog (Rung 2 - Warning)**
Instead of "Are you sure?", the dialog must state exact facts: "Delete workspace 'Production' and its 15 projects permanently?"
* **Pros**: Easy UI change.
* **Cons**: Weaker than typing to confirm, but better than "Are you sure?".

## Open Questions
> [!CAUTION]
> 1. Is workspace deletion currently a hard delete on the backend? 
> 2. Are you open to making backend changes (Option 1), or do we need a UI-only fix today (Option 2/3)?

## Proposed Changes
Once an option is selected, I will update this plan with the specific code changes required for your codebase.

## Verification Plan
### Manual Verification
1. Attempt to delete a workspace reflexively. The system should prevent accidental deletion either by allowing recovery (undo/trash) or by structurally preventing the reflexive click (typing name).