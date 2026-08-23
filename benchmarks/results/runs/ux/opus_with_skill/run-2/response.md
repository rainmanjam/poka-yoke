Not quite — it's the weakest device on the ladder aimed at your most irreversible action, and the symptom you described is evidence it won't work.

**Why the modal fails here.** "Are you sure?" asks about *resolve*. Your users' resolve was fine — they meant to delete a workspace, just not *that* one. It's a misidentification error, and a dialog that doesn't name the object catches none of it. Worse, every user sees it on every legitimate delete, so within a week it's reflex-clicked. That's rung 0 with friction attached.

The panic email is the real signal: **deletion is unrecoverable and users have no path back except you.**

★ Insight ─────────────────────────────────────
The poka-yoke ladder ranks by *what happens when the mistake occurs*, not by how loud the warning is. A modal is Warning (rung 2) at best. Soft-delete is Control (rung 1) — the mistake becomes a non-event, no gate needed.
Undo beats confirm because confirmation taxes every correct action to guard a rare wrong one; undo taxes only the wrong one.
─────────────────────────────────────────────────

**What I'd build instead**, in order:

1. **Soft-delete + 30-day trash.** `deleted_at` timestamp, filtered out of every read path, hard-deleted by a job after retention. The panic email becomes a "Restore" button. This is a backend change, which is why people reach for the modal instead — but it's the only one that actually closes the hazard.
2. **Grace-period undo toast.** Delete immediately, show "Workspace *Acme Q3* deleted — Undo" for ~10s. Zero friction on the happy path.
3. **Only if a hard delete stays reachable:** type-to-confirm the workspace name, plus the scale — "This deletes **47 projects, 1,204 files, 12 members**". A count is the inspection; "this cannot be undone" is not.

Two things worth checking while you're in there: whether the delete button sits next to something benign in the workspace toolbar (mis-clicks live there — move it into settings), and whether the *server* refuses deletes from non-owners or the UI just hides the button.

---

**One decision I'd rather you make than guess at** — retention semantics during the grace window. These are business calls, not engineering ones:

- Does a soft-deleted workspace still consume a seat / count toward the plan limit? (Bill for it and users complain; don't and you've built a free storage loophole.)
- Can the workspace *name* or slug be reused immediately, or is it held? (Releasing it makes restore ambiguous; holding it confuses users who want to recreate.)
- Who can restore — any member, or only the owner who deleted it?

Tell me those three and I'll write the schema change, the read-path scoping, and the restore endpoint. If you'd rather sketch it, the shape is a `deleted_at`/`deleted_by` pair plus a `purge_after` column — the third one is what lets you vary retention by plan later without a migration.