Using poka-yoke:ux to evaluate this — a modal is the weakest device on the ladder for this problem.

**The core issue:** confirmation dialogs that fire often stop being decision points. If "delete workspace" isn't rare, users will click through "Are you sure?" on reflex — same muscle memory as dismissing a cookie banner. It adds friction to every legitimate delete without stopping the accidental ones, which is exactly the panic-email pattern you're describing now with no gate at all.

**Preference order for destructive actions (strongest first):**
1. **Make it reversible** — soft-delete with a retention window (e.g. 30 days), workspace goes to trash, can be restored. No gate needed at all because the mistake has no permanent consequence. This is a backend change, not a UI change, which is why it's under-used.
2. **Grace-period undo** — delete immediately, show "Workspace deleted. Undo" for ~10s. Zero friction on the happy path, full recovery on the mistaken one.
3. **Type-to-confirm** — typing the workspace name, for genuinely high-blast-radius/irreversible cases. Reserve this for things that truly can't be undone.
4. Generic "Are you sure?" modal — bottom of the list. If you do add one, it needs to name the specific thing ("Delete workspace 'Acme Corp' and its 14 members?"), not just ask about resolve.

**My recommendation:** skip the modal, ship soft-delete + 30-day trash + an undo toast on the delete action itself. That's rung 1 (the mistake stops having consequences) instead of rung 2 (a warning people learn to ignore), and it directly kills the support-panic pattern since "I deleted it by accident" becomes self-service restore instead of a ticket.

Three things that'd shape the implementation if you want to go this route: what happens to billing/seats during the grace period, whether the workspace's URL slug gets released immediately or held for 30 days, and who's allowed to restore (any admin, or only whoever deleted it).