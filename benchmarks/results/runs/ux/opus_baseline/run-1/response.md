Short answer: no — not as the main fix. And worth flagging, you and I landed on this same question yesterday (`.remember/today-2026-08-21.done.md`, 23:19) and rejected the modal then; implementation of the alternative is still pending.

**Why the modal doesn't fix it**

The panic emails are the tell. Users aren't emailing because they weren't warned — they're emailing because the deletion is *unrecoverable*. A modal doesn't change that; it just adds a step in front of the same cliff. And "Are you sure?" asks about the user's resolve, which was never in question. They meant to click delete. They were on the wrong workspace.

`★ Insight ─────────────────────────────────────`
The poka-yoke ladder ranks "Are you sure?" at rung 0 — same tier as a tooltip, because it relies on the user reading and reconsidering. Users who see a dialog often develop click-through blindness; the dialog then protects nobody while taxing every legitimate delete. Worse, it trains dismissal of the dialogs that *do* matter.
`─────────────────────────────────────────────────`

**What actually closes it**

1. **Soft-delete with retention** (rung 1). Workspace is marked deleted, hidden from the UI, purged after N days. The mistake now has no permanent consequence — so it needs no gate at all. This is a backend change, which is exactly why teams reach for the modal instead.
2. **Grace-period undo.** Delete fires immediately, toast shows "Workspace deleted. Undo" for ~10s. Zero friction on the happy path, full recovery on the mistaken one.
3. **Self-serve restore** in a Trash view for the rest of the window — this is what kills the support emails, not the modal.

One diagnostic question that changes the shape: **when support gets these emails today, can they restore the workspace?** If yes, you already have soft-delete and this is purely a UI gap — Trash + undo is a day of work. If no, the data is genuinely gone and the retention change is the whole project.

**If you still want a gate**

Keep one, but only for the irreversible purge, and make it do inspection instead of asking about resolve:

> Delete **Acme Production** — 14 projects, 3,204 files, 8 members?

That names the object and the count, so a user on the wrong workspace sees it. GitHub-style type-the-name is defensible here too, given blast radius — but only in front of permanent purge, never in front of a recoverable delete.

**The decision that's yours to make**

Two things shape this and depend on your product, not on the pattern:

- **Retention window.** 7 days is cheap and catches most panic; 30 days catches the "we deleted the staging workspace before the quarterly audit" case but means you're storing data customers believe is gone — which has contractual and GDPR-deletion implications worth checking.
- **Who can restore.** Any member, or only owners/admins? Restore is a resurrection of access, so it inherits the workspace's authz question.

Tell me which way you want those, plus whether support can currently recover, and I'll write the implementation against your actual code — this repo is the poka-yoke plugin, so point me at the app.