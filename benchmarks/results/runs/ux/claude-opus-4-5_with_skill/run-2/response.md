**Short answer: no, an "are you sure?" modal won't help.**

Users develop click-through blindness after seeing the same dialog fifty times. They'll hit "Confirm" with the same muscle memory they use for "OK" — which is why people are emailing support despite presumably already clicking past *something*.

`★ Insight ─────────────────────────────────────`
Shingo's poka-yoke ladder says a confirmation dialog that asks "Are you sure?" sits at **rung 0** — it relies on people reading and caring, which degrades immediately. A dialog that names the *specific object* being destroyed is rung 2 (warning). But the real question is: **why is this irreversible at all?**
`─────────────────────────────────────────────────`

The fact that support can restore these workspaces means you already have recoverability somewhere. The right fix — which reaches **rung 1 (control)** — is:

| Device | What it does | Rung |
|--------|--------------|------|
| **Soft-delete + trash** | Workspace moves to a "Recently Deleted" folder. User can restore it themselves. No dialog needed. | Control |
| **Grace-period undo** | "Workspace deleted. [Undo]" toast for 10 seconds. Zero friction, full recovery. | Control |
| **Type-to-confirm** | Type workspace name to delete (GitHub-style). Reserve for bulk or high-value. | Control |
| "Delete `workspace-name`?" dialog | Better than "are you sure?" but still rung 2. | Warning |

**Recommendation:** Implement soft-delete with a 30-day trash retention and an "Undo" toast on the delete action. Support tickets go to zero because users can self-recover. The "are you sure?" modal stays on the shelf.

Want me to audit the delete code path to see what reversibility you already have, or sketch the soft-delete + undo-toast implementation?