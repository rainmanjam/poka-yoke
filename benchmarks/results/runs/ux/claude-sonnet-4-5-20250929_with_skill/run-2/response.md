Not really — that modal won't actually protect anyone.

The problem: **confirmation dialogs that users see repeatedly become invisible**. People develop click-through blindness and hit "Confirm" reflexively. It adds friction to every legitimate deletion while doing nothing to prevent the mistaken one. It's the UI equivalent of a comment saying "be careful" — present, visible, and inert.

Here's the poka-yoke ladder for destructive actions, strongest first:

**1. Make it reversible** (best)
- Soft-delete workspaces instead of hard-deleting them
- Add a "Trash" where deleted workspaces live for 30 days
- Users can self-serve restore without emailing support
- **This eliminates the problem** — no gate needed, no panic, no support tickets

**2. Grace-period undo**
- Delete immediately, show "Workspace deleted. Undo" toast for 10 seconds
- No friction on happy path, full recovery on mistaken path
- Like Gmail's undo-send

**3. Require proportional action**
- Type the workspace name to confirm: `DELETE production-api`
- Works because it *cannot be done reflexively*
- Only use for truly irreversible, high-blast-radius actions

**4. Specific consequence dialog**
- "Delete workspace 'Q4-analytics' and 127 dashboards permanently?"
- This does **fixed-value inspection** — the count and name are facts to check
- "Are you sure?" is not a check — it asks about resolve, not facts

## What I'd recommend

Can you add a backend trash/soft-delete system? That's the real answer — makes the mistake have no permanent consequence. If you can't touch the backend right now:

- Grace-period undo (option 2) as a stopgap
- Or type-to-confirm (option 3) if deletion is truly permanent

Before I say more: **does your backend support soft-delete or versioning?** That changes which device is viable.