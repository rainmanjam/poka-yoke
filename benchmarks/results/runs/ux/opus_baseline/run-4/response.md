Honest answer: no, I'd push back on that one. It's the weakest device available for this problem, and your own description of the symptom is the reason why.

**The tell is "emailing support in a panic."** That means the workspace is *gone* — support has to restore from a backup or tell them it's unrecoverable. The modal doesn't touch that. Even if it cuts accidental deletes by half, the half that get through still produce the exact same support email. You'd be reducing the frequency of an unbounded loss instead of bounding the loss.

**And "Are you sure?" specifically asks the wrong question.** It asks about the user's *resolve*, which was never in doubt — they meant to click delete, they just had the wrong workspace selected, or didn't realize what deletion took with it. Resolve isn't the thing that failed. A dialog reading "Delete **Acme Production** — 47 projects, 1,204 files, 12 members?" would at least be doing real inspection, because it names facts the user can check against their intent. But a generic confirm is dismissed reflexively within about two weeks of shipping.

★ Insight ─────────────────────────────────────
There's a preference order for destructive actions, strongest first: make it reversible → grace-period undo → proportional action (type the name) → specific-consequence dialog. Confirmation is *last*. The reason reversibility is under-used isn't that people don't know it's better — it's that it's a backend change and a modal is an afternoon of frontend work.
─────────────────────────────────────────────────

**What I'd build instead:** soft-delete with a ~30-day trash, plus an "Undo" toast right after the click. Set `deleted_at`, exclude it from every workspace query, run a purge job after the retention window. Now the accidental delete costs the user four seconds instead of a support ticket, and support gets a self-serve restore button rather than a backup request.

That's genuinely more work than the modal — maybe two or three days rather than an afternoon — mostly in auditing every query that lists workspaces so a soft-deleted one can't leak back into the UI. The modal is the cheaper fix; it just doesn't fix this.

If you want a gate on top of soft-delete, use type-to-confirm (GitHub's repo-deletion pattern) rather than a yes/no — it can't be done reflexively. But honestly, once delete is reversible, you may not need a gate at all.

Three things I'd need from you before writing code, since they're product calls rather than technical ones:

1. **Billing and seats during the grace period** — does a trashed workspace still count toward the plan? Charging for it is confusing; not charging makes delete-then-restore a way to skip a billing cycle.
2. **Slug reuse** — can someone claim `acme-prod` while the old one sits in trash? Blocking it is safer, but it leaks the existence of a deleted workspace to outsiders.
3. **Who can restore** — the deleter, any admin, or support only?

Want me to look at the actual delete path in your codebase and scope this out concretely? I'd want to see how workspaces get queried before promising the soft-delete audit is small.