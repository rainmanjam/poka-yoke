# Implementation Plan: Preventing Accidental Workspace Deletion

## Goal Description
Prevent users from accidentally deleting their workspaces, which currently results in data loss and panicked support emails. 
The initial proposal was to add an "are you sure?" modal before the deletion occurs.

## User Review Required

> [!WARNING]
> **An "Are you sure?" modal is not recommended.**
> 
> According to the Poka-Yoke UX methodology, an "Are you sure?" modal sits at **Rung 0** (relies on reading). Users develop *click-through blindness*—they press "Confirm" with the same reflex they press "OK". This means the dialog protects nobody while adding friction to every legitimate action. 

To actually solve the problem, we must apply a proper mistake-proofing device. Below are three alternative approaches ranked by their Poka-Yoke effectiveness.

## Open Questions

> [!IMPORTANT]
> Which of the following approaches is most feasible for your current backend architecture? Option 1 is the most robust, but requires backend changes. 

## Proposed Changes

### Option 1: Soft-Delete with Retention (Rung 1: Control) - **Recommended**
Make the action reversible on the backend. This is the strongest device because the mistake has no permanent consequence and needs no gate at all.

*   **UI Flow:** Remove the confirmation modal entirely. When the user clicks "Delete", immediately hide the workspace and show a toast notification: "Workspace moved to trash. [Undo]".
*   **Backend:** Instead of dropping the database records, add a `deleted_at` timestamp. 
*   **Cleanup:** Implement a background job to permanently delete records where `deleted_at` is older than 30 days.
*   **Benefit:** Users can recover from their own mistakes instantly without contacting support.

### Option 2: Grace-Period Undo (Rung 1: Control)
If you cannot store soft-deleted data, delay the execution.

*   **UI Flow:** When the user clicks "Delete", the UI optimisticly removes the workspace and shows a toast: "Workspace deleted. [Undo]" with a 5-10 second countdown.
*   **Execution:** The frontend holds the API request. If the timer expires, the delete request is sent. If the user clicks Undo, the request is cancelled and the UI reverts.
*   **Benefit:** Zero friction on the happy path, full recovery on the mistaken one.

### Option 3: Type-to-Confirm (Rung 2: Warning)
If the action *must* be immediate and irreversible, force the user out of their auto-pilot reflex.

*   **UI Flow:** Show a modal that names the specific workspace and its contents (e.g., "Delete 'Production' and its 12 projects?"). Require the user to type the exact name of the workspace into a text field to enable the "Delete Forever" button.
*   **Benefit:** This is a *forcing function* that requires an action proportional to the consequence. It cannot be done reflexively.

## Verification Plan
Once an option is selected, we will:
1. Implement the chosen UX pattern.
2. Verify that reflexive, accidental clicks no longer result in irreversible data loss.
3. Ensure the UI clearly communicates the state (either via undo toasts or clear type-to-confirm instructions).