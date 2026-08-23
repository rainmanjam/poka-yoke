Using `poka-yoke:ux` — this is squarely a destructive-action design question.

Honest answer: **a modal alone won't fix it.** It's the weakest device on the ladder for exactly this failure mode.

## Why

The users emailing support in a panic *already clicked through a confirm* in every product they've ever used. A dialog they see repeatedly stops being a decision point — they develop click-through blindness and press Confirm with the same reflex as OK. You'd add friction to every legitimate delete and still get the panicked emails.

Worse, the tell is in the support tickets themselves: they're emailing **after**, asking for the data back. The problem isn't that they weren't warned. It's that the action is unrecoverable.

## What actually closes it

The preference order for destructive actions, strongest first:

1. **Soft-delete + retention window** — the real fix. Mark deleted, hide from UI, purge after N days. Now the mistake has no permanent consequence, support can self-serve a restore instead of escalating to engineering, and you need almost no gate at all.
2. **Grace-period undo** — "Workspace deleted. Undo" toast for ~10s. Zero friction on the happy path.
3. **Type-to-confirm** the workspace name — GitHub's repo-delete pattern. Can't be done reflexively.
4. A dialog stating the **specific consequence** — "Delete `acme-prod`, 14 projects, 1,204 files?" That's real inspection. "Are you sure?" asks about resolve, and resolve isn't what's in question.

My recommendation: **1 + 2, and skip the modal entirely.** If workspace delete is genuinely high-blast-radius for you (shared org data, billing implications), add 3 on top — but 3 without 1 is still a one-way door.

`★ Insight ─────────────────────────────────────`
The reason this repo keeps landing on soft-delete over confirms: a confirm is *training* (degrades with exposure), soft-delete is a *device* (works whether or not anyone is paying attention). Same distinction as CLAUDE.md's "if your change relies on someone remembering something, it is not finished."

The catch — soft-delete is a backend change, not a UI change. That's precisely why teams reach for the modal instead. It's the cheap thing that looks like the fix.
`─────────────────────────────────────────────────`

## Two calls that are yours, not mine

Before I write anything, these shape the implementation and I don't want to guess:

- **Retention window.** 7 days is cheap and covers "oh no" within a workday. 30 days covers "the person who deleted it was on PTO" but means you're storing — and possibly billing for — dead workspaces. If you're under any deletion-SLA commitment (GDPR erasure requests, a SOC2 control, an enterprise DPA), that caps you.
- **Who can restore.** Self-serve from a Trash view is the whole point — it takes support out of the loop. But if a deleted workspace's members lose access on delete, nobody's left who *can* restore it, and you're back to support tickets.

Tell me the window and the restore actor and I'll build it — or point me at the delete handler and I'll read what's there first and come back with a concrete diff.