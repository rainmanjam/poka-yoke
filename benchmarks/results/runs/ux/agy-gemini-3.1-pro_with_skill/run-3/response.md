## Goal Description
The goal is to prevent users from accidentally deleting their workspaces, which currently results in data loss and panic-driven support tickets. The proposed solution is to implement an interface device to mistake-proof this flow.

## User Review Required
> [!CAUTION]
> The proposed "Are you sure?" modal is not recommended. It asks about resolve rather than facts, and users quickly develop click-through blindness, clicking "Confirm" reflexively. It will not stop the accidental deletions.

Based on the *poka-yoke* methodology for interfaces, we have better options depending on the backend capabilities. Please select from the following alternatives in order of preference:

1. **Make it reversible (Soft Delete - Rung 1 Control)**
   *The strongest device.* Instead of deleting immediately, we move the workspace to a "Trash" state with a retention period (e.g., 30 days). No confirmation dialog is needed at all, removing friction while offering complete recovery.
   *Requires backend support.*

2. **Type-to-Confirm (Rung 2 Warning)**
   If deletion must be genuinely irreversible, require the user to type the workspace's exact name to confirm. This action cannot be done reflexively and forces them to acknowledge *which* workspace they are deleting.

3. **Concrete Confirmation Dialog (Rung 2 Warning)**
   If we must use a simple modal, it needs to be concrete:
   - **Name the object:** "Delete workspace 'production-api'?"
   - **State the scale:** "This will permanently delete 14 projects and 3,201 files."
   - **Action-oriented button:** The button must say "Delete workspace", not "OK".

## Open Questions
> [!IMPORTANT]
> - Does our backend currently support soft-deletes or a trash state for workspaces? If so, we should implement Option 1.
> - If it doesn't, is it worth building that capability now, or should we implement Option 2 (Type-to-confirm) as an immediate interface fix?

## Proposed Changes
No code changes will be made until a specific option is chosen. Once an option is selected, I will update this plan with the specific component modifications.

## Verification Plan
### Automated Tests
- To be determined based on the selected option.
### Manual Verification
- Verify the destructive action behaves according to the selected UX pattern.
- Ensure the user cannot bypass the protection via keyboard shortcuts or fast double-clicking.