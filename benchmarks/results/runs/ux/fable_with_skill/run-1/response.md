Short answer: **no — an "are you sure?" modal is the weakest device on the ladder, and it won't stop the emails.**

## Why the modal won't work

The poka-yoke `ux` skill is blunt about this: a generic confirmation asks about the user's *resolve*, not about *facts*. Users who delete a workspace by accident were already sure — they thought it was a different workspace, or they thought "delete" meant "leave", or they clicked the wrong row. "Are you sure?" gets the same reflexive "Yes" as the real deletes. Within a few weeks it's click-through blindness, and you've added friction to every legitimate delete while protecting nobody. It's the UI equivalent of a comment saying "be careful" — rung 0.

The support emails are the actual tell: the users aren't asking "how do I stop doing this?", they're asking **"can you get it back?"** That's a reversibility problem, not a confirmation problem.

## What to do instead (strongest first)

1. **Soft-delete with a trash/retention period — rung 1, Control.** Mark the workspace deleted, hide it, purge after 30 days, let the user (or support, in one click) restore it. Now the mistake has *no permanent consequence* and the panic emails turn into "click Restore in Settings → Trash." This is the real fix, and it's underused because it's a backend change, not a UI one.

2. **Grace-period undo on top of that.** Delete immediately, show "Workspace *Acme Marketing* deleted. **Undo**" for ~10 seconds. Zero friction on the happy path, instant recovery on the mistaken one.

3. **If something genuinely can't be soft-deleted** (e.g. it frees a globally unique slug, or triggers billing cancellation), then gate *that* with **type-to-confirm** — the user types the workspace name. Reserve it for the irreversible case only; everywhere else it becomes copy-paste theater.

4. **If you still ship a dialog**, make it a real one, which needs all four of:
   - Names the object: "Delete **Acme Marketing**?" not "this workspace"
   - States the scale: "14 members, 2,310 documents" — a count is fixed-value inspection, and it's what catches the wrong-row mistake
   - States reversibility honestly: "Recoverable for 30 days from Trash"
   - Button says the verb: **Delete workspace** / Cancel — and focus defaults to Cancel

Also worth checking while you're in there: is Delete sitting next to a frequent benign action (Leave, Settings, Save) with the same visual weight? Adjacency causes a lot of "accidental" deletes that no dialog fixes.

## Recommendation

Do (1) + (2). Keep the dialog only if it's the rung-2 version in (4), and only for whatever remains irreversible after soft-delete exists. Rung achieved: Control — the mistake still happens, it just stops being a defect. What stopped me going higher: nothing; you can't prevent a human from clicking the wrong row, so making it harmless *is* the top of the ladder here.

If you want, point me at the delete handler and the workspace model and I'll propose the soft-delete shape (deleted_at column, filtered default scope, restore endpoint, purge job) before touching anything.