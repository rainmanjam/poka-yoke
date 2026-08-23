Not quite. A confirmation modal is rung 0 here—it relies on the user *reading and thinking* rather than the interface *preventing the mistake*. And there's a harsh reality in the UX literature: **confirmation dialogs that appear frequently cause click-through blindness**. Users trained by dozens of benign "OK" clicks will dismiss "Are you sure?" reflexively.

From the UX skill:

> A confirmation dialog a user sees fifty times a day stops being a decision point… the dialog protects nobody while adding friction to every legitimate action.

Your situation—users *keep* accidentally deleting workspaces—is exactly where a modal *fails*. A generic dialog adds friction to every legitimate workspace deletion while protecting almost nobody from the panicked accidental ones.

**Better approach** (ranked strongest first):

1. **Soft-delete + trash (rung 1 — control).** When a user deletes a workspace, move it to trash rather than destroying it immediately. Keep it for 30 days, then auto-purge. The mistake becomes reversible and needs no gate at all.

2. **Grace-period undo (rung 2 — warning).** Delete immediately, but show "Workspace deleted. [Undo]" as a toast for 10 seconds. Full recovery on mistake, zero friction on the happy path. This is what Gmail does.

3. **Type-to-confirm (rung 3 — warning, if reversible is too expensive).** Only for genuinely irreversible actions: require the user to type the workspace name to confirm deletion. It cannot be done reflexively. Use sparingly—used everywhere it becomes theater.

Which of these fits your setup? If the workspace deletion is truly irreversible once performed (data immediately purged from all systems), soft-delete with a trash bin is the standard answer. If there are hard constraints preventing that, let's look at the type-to-confirm or a delayed-commit approach instead.