Short answer: no, a plain "are you sure?" modal won't fix this — and we actually worked through this exact question earlier in this session, landing on a different device.

**Why a confirm modal is the wrong tool here:** it's rung-0 on the poka-yoke ladder — it relies on the user reading it. If someone deletes a workspace by accident today, a modal doesn't stop a second accident; people click through confirm dialogs on reflex the moment they see them often enough. It also does nothing for the panic-email problem, because the damage is already permanent by the time support gets involved.

**What actually fixes "accidental + irreversible + panicked email to support":** make the delete reversible instead of gating it.
1. Soft-delete + 30-day trash — deleting a workspace moves it to a recoverable state, not `DROP`. This alone kills most of the support tickets, since "I panicked" turns into "click restore."
2. Grace-period undo toast — "Workspace deleted. Undo" for ~10s on the action itself, no dialog in the way at all.
3. Keep a lightweight confirm only if you want a second gate, but make it name the actual object ("Delete Acme Corp workspace — 4 seats, 1,204 files?"), not a generic "are you sure?"

From earlier tonight's session, this was already scoped as: soft-delete + 30-day trash + undo toast, blocked on three decisions before implementation — what happens to billing/seats during the grace period, whether the workspace slug can be reused during that window, and who has permission to restore. Do you want to pick those up now, or was tonight's direction a false start and you want to go with just the modal instead?