Using ux to evaluate the confirm-modal proposal.

Short answer: it'll help a little, but it's the weakest device on the ladder, and for a mistake happening often enough that people are emailing support in a panic, it probably won't hold.

**Why "are you sure?" specifically underperforms here:**
- A generic confirm dialog is rung 0 in practice — "Are you sure?" asks about the user's resolve, not about facts. It doesn't name what's being deleted or its scope, so it's exactly the kind of dialog people click through on reflex once they've seen it a few times. It stops nobody who's already committed to the click, and it adds friction to every legitimate deletion.
- If workspace deletion is rare per-user, click-through blindness won't have set in yet, so a confirm dialog will genuinely catch some fraction of mistakes. But it caps out low, and it does nothing for the case where someone *meant* to delete but didn't realize what was in the workspace.

**What actually closes this (in order of strength):**
1. **Make it reversible** — soft-delete with a retention window (e.g., 30 days), so an accidental delete has no permanent consequence and needs no gate at all. This is a backend change, not a UI change, which is why it's under-used, but it's the real fix.
2. **Grace-period undo** — delete immediately, show "Workspace deleted. Undo" for ~10s, with the actual purge deferred. Zero friction on the happy path, full recovery on the mistaken one.
3. If you still want a dialog on top of that, make it name the specific consequence ("Delete 'Acme Marketing' — 4 members, 218 documents?") rather than a bare "are you sure?" — that's fixed-value inspection and it actually informs the decision.

Note: earlier in this session we already worked through this exact scenario and landed on soft-delete + 30-day trash + undo toast, blocked on three business decisions — what happens to billing/seats during the grace period, whether the workspace slug gets released or reserved during that window, and who's allowed to trigger a restore. Is that still where you want to take it, or has something changed and you specifically want the modal as a stopgap while soft-delete gets scoped?