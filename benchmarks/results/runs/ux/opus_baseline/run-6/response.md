Using poka-yoke:ux — and this one lands on the skill's sharpest rule: **undo beats confirm.**

## Honest answer: no, not as the primary fix

A confirmation modal is the intuitive move, but it fails specifically in the case you're describing. The users deleting workspaces by accident aren't people who lack resolve — they're people who clicked the wrong row, or thought they were in the staging workspace. "Are you sure?" asks about resolve. Their resolve was fine; their *target* was wrong. The modal doesn't correct that, and after the third one they'll click through it at the same speed they clicked delete.

Worse, it converts a recoverable-if-you-build-it problem into a permanently-lost one with a receipt that says the user agreed.

## What actually stops the panicked support emails

Soft-delete + 30-day trash + an undo toast. The workspace disappears from the UI immediately (feels the same as today), a `Deleted. Undo` toast sits there for ~10s, and the row stays restorable in Trash for 30 days. Support's job changes from "restore from backup, escalate to eng" to "click Restore."

That's rung 1 on the ladder — the mistake stops having a permanent consequence, so it stops needing a gate.

If you want a gate *too*, make it the useful kind: not "this cannot be undone," but "Delete **acme-prod** — 12 projects, 4,312 files, 8 members?" Naming the object and the counts is what catches the wrong-workspace click. Save type-the-name-to-confirm for the permanent purge inside Trash, where it genuinely is irreversible.

`★ Insight ─────────────────────────────────────`
- The reason confirm-dialogs feel like a fix is that they're a **frontend** change and soft-delete is a **backend** one. The cheaper device is almost always the weaker one — that's exactly the gradient this repo's CLAUDE.md warns about ("if your change relies on someone remembering something, it is not finished"). A modal relies on the user reading.
- Undo has a second advantage that's easy to miss: it costs *zero* friction on the ~99% of deletions that are intentional. Confirmation taxes every legitimate delete to maybe-catch the rare wrong one.
`─────────────────────────────────────────────────`

## Before I build anything

We walked this same path earlier today (05:18–06:00) and stalled on three decisions that are yours, not mine — they're product calls with real revenue and support implications:

1. **Billing and seats during the grace period.** Does a soft-deleted workspace keep consuming paid seats for 30 days? Charging for a deleted thing generates its own support tickets; not charging makes delete-then-restore a free-month exploit.
2. **Slug reuse.** If `acme-prod` is in Trash, can someone create a new `acme-prod`? Freeing the slug makes restore ambiguous; holding it for 30 days confuses people who deleted deliberately to rename.
3. **Who can restore.** Only the deleter? Any workspace admin? Org owners? This is an authz decision and it interacts with the fact that deleting a workspace may have removed the membership records that would grant that permission.

Pick those three and tell me the scope you want (schema + API, or full UI too), and I'll implement it. If you'd rather ship the modal today as a stopgap while the soft-delete lands, say so — I'll build the consequence-naming version rather than the "are you sure?" one, since they cost the same to write.