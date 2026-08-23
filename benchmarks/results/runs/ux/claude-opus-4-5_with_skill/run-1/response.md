## Poka-yoke analysis: workspace deletion

**Short answer: no.** An "are you sure?" modal is rung 0 — it relies on the user reading it, and they won't. Users who delete workspaces fifty times a day will click through with the same reflex they press "OK". The panicked support emails will continue.

`★ Insight ─────────────────────────────────────`
Shingo's core principle: a comment, a warning, a dialog saying "be careful" is not a device — it's training. Training degrades. The fact that users *keep* emailing support means the current friction (or proposed modal) doesn't work because the action is still irreversible when the mistake happens.
`─────────────────────────────────────────────────`

### The preference ladder for destructive actions

| Approach | Rung | Why |
|---|---|---|
| **Soft-delete + trash with 30-day retention** | 1 (Control) | Mistake has no permanent consequence. No dialog needed at all. User self-recovers. |
| **Grace-period undo toast** ("Deleted. Undo" for 10s) | 1 (Control) | Zero friction on happy path, full recovery on mistake. Gmail undo-send model. |
| **Type workspace name to confirm** | 1 (Control) | Cannot be done reflexively. Reserve for *truly* catastrophic (account deletion). Overkill here. |
| **Dialog naming the specific workspace + contents** | 2 (Warning) | Better than "are you sure" but still dismissable. |
| **"Are you sure?" modal** | 0 | Click-through blindness. Protects nobody, adds friction to everyone. |

### Recommendation

**Soft-delete + trash.** The workspace moves to a "Recently Deleted" section with a 30-day retention period. No confirmation dialog needed — the action is reversible. Users who panic just go to trash and restore. Support tickets drop to near zero.

If backend constraints make soft-delete expensive, fall back to **grace-period undo**: perform the delete immediately, show "Workspace deleted. Undo" toast for 10 seconds, defer the actual hard delete until the window closes.

Both are rung 1 (Control). Both require backend changes, not just a modal. That's intentional — the real fix for "users keep deleting things" is *make deletion recoverable*, not *make deletion annoying*.

Want me to audit the current delete code path to see what's feasible?