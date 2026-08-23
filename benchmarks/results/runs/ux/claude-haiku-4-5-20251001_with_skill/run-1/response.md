**Not with just a modal, no.** A confirmation dialog sits at rung 2 (warning), but the poka-yoke UX skill shows this is the weakest choice for destructive actions—and it won't solve your support email problem.

From the skill:

> A confirmation dialog a user sees fifty times a day stops being a decision point. They develop click-through blindness and press "Confirm" with the same reflex they press "OK" — which means the dialog protects nobody while adding friction to every legitimate action.

Your users are panicking because the deletion is **irreversible**. A generic "Are you sure?" modal doesn't fix that—it just adds a button they'll click reflexively on the next legitimate delete, then ignore the next time they do it by accident. You've just trained everyone to ignore your safety device.

The preference order for destructive actions (strongest first):

1. **Make it reversible.** Soft-delete with a trash/retention period. No modal needed; the mistake has no permanent consequence. ✓ **Rung 1 (Control)**
2. **Grace-period undo.** Delete immediately, show "Deleted. Undo" toast for 30 seconds. Full recovery, no friction on normal use. ✓ **Rung 2 (Warning, done right)**
3. **Type-to-confirm.** "Type 'workspace-name' to confirm." Only for genuinely irreversible, high-blast-radius actions.
4. **Confirmation dialog naming the exact consequence.** "Delete workspace 'acme-corp' and 3,400 files permanently?" — not "Are you sure?"

I see from your earlier session notes that soft-delete + 30-day trash + undo toast was already the recommendation, but it's blocked on three design decisions: billing/seats during grace period, slug reuse, and restore permissions. **Those are the real problems to solve**—the modal won't help until you know the answers to those.

What's blocking the design decisions?