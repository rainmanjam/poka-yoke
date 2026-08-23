Short answer: it'll help a little, but it's the weakest device on the ladder for this problem.

**Why a modal underperforms here:** "Are you sure?" dialogs that appear on every delete get click-through blindness — users start pressing "Confirm" reflexively, the same way they dismiss cookie banners. It stops zero accidental deletes from someone moving fast, and it still won't stop the panicked-email pattern, because the modal fires *before* the mistake, when the user hasn't yet realized they clicked the wrong thing.

**Stronger fix, same effort tier:** soft-delete + grace-period undo.
- Delete happens immediately (no friction added to the 99% of deletes that are intentional).
- Workspace goes to a 30-day trash instead of being purged.
- Show a "Workspace deleted. Undo" toast for ~10s.
- Support's panic-email path becomes self-serve: "go to Trash, restore it" instead of an escalation.

This is rung 1 (control — the mistake literally has no permanent consequence) vs. a modal, which is rung 2 at best and degrades toward rung 0 with repetition.

If you still want the modal as a stopgap, put it on top of soft-delete rather than instead of it — but the soft-delete is what actually kills the support tickets.

Three things you'd need to decide before I'd build this: what happens to billing/seats during the 30-day grace period, whether the workspace slug/URL gets released for reuse before or after the trash window closes, and who besides the deleter can restore it (owner-only vs. any admin). Want me to draft the schema/API shape for that, or should we scope it down to just the undo-toast piece first?