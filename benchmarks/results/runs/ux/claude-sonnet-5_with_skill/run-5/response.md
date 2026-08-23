Short answer: a plain "are you sure?" modal is the weakest fix on the ladder — skip it in favor of an undo pattern.

**Why the modal won't fix your panic emails:** a confirm dialog is rung 2 at best (warned but still possible), and for a frequent action it degrades to rung 0 fast — users see it dozens of times, build click-through muscle memory, and confirm it the same reflex as an "OK" button. It stops the *careful* deleter, not the person who fat-fingers it. And "Are you sure?" tests resolve, not facts — it doesn't even tell them what's about to be destroyed.

**What actually kills the support emails:** make the delete reversible so there's nothing to panic about.

1. **Soft-delete + trash, ~30 day retention.** Delete moves the workspace to a recoverable state instead of destroying it. This is the real fix — no gate needed at all — but it's a backend change, not just a modal.
2. **Grace-period undo toast.** Delete fires immediately, "Workspace deleted. Undo" persists for ~10s. Zero friction for the 99% of intentional deletes, full recovery for the fat-finger case.
3. Only if the delete must stay instantly permanent: type-to-confirm (type the workspace name), sized to the blast radius — not a generic "are you sure."

A modal is fine to *keep* alongside soft-delete for the small class of accidents that happen inside the click itself, but it shouldn't be your only device — most panicked support emails are "I clicked delete and now I need it back *right now*," which a modal doesn't solve once they've already confirmed.

**Before this is implementable, three things need deciding:**
- Grace period behavior for billing/seats — does deleting immediately stop billing, or only after the retention window expires?
- Slug/name reuse — can someone create a new workspace with the same name while the old one is still in trash?
- Who can restore — original owner only, or any prior admin?

Want me to sketch the soft-delete schema + undo toast component, or scope just the confirm-modal-as-interim-step while backend work is planned?