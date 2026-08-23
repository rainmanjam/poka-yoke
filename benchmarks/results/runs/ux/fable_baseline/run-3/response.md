Honest answer: it'll help a little, and you'll be back here in six months. An "are you sure?" modal is the weakest device on the ladder — it asks about the user's *resolve*, not about the *facts*, and anyone who deletes things regularly learns to click through it on reflex. The panicked emails you're getting are from people who were *sure* when they clicked.

What actually fixes the support load, strongest first:

1. **Make deletion reversible.** Soft-delete with a trash/retention window (30 days is typical). Now the mistake has no permanent consequence, and support's answer becomes "click Restore" instead of "sorry." This is the real fix — it's a backend change, which is why it gets skipped, but it's the only option that makes the panic email go away entirely.
2. **Grace-period undo.** Delete immediately, show "Workspace deleted — Undo" for ~10s. No friction on the happy path, full recovery on the mistaken one. Pairs naturally with (1).
3. **If it genuinely must be irreversible** (compliance, storage cost), use type-to-confirm: user types the workspace name. That can't be done reflexively, unlike clicking OK.
4. **If you still want a modal**, make it state the specific consequence: "Delete *acme-prod* — 14 projects, 3 collaborators, 2.1 GB — permanently?" That's a real check. "Are you sure?" is not.

Also worth checking while you're in there: is Delete visually adjacent to or styled like a benign action (Archive, Leave)? Mis-clicks are often the actual root cause, and no dialog fixes a button that's in the wrong place.

★ Insight ─────────────────────────────────────
- Confirmation dialogs have a known failure mode called click-through blindness; frequent ones actively train users to dismiss the rare ones that matter.
- Reversibility removes the need for a gate entirely — it's "rung 1" in this repo's ladder, the modal is "rung 0" (relies on reading).
- The panic email *is* your metric: count them before and after, so you know whether the change worked rather than assuming.
─────────────────────────────────────────────────

**My recommendation:** soft-delete + undo toast, with the modal only if the workspace has collaborators (blast radius beyond the clicker). If you want, point me at the delete handler and I'll draft it.