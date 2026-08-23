Using **poka-yoke** → routed to the **`ux`** mode (destructive action in a UI), plus the `ux-patterns` and hazard-catalog references.

## Short answer: no, not as the fix

The panic emails aren't telling you people clicked too fast. They're telling you **the delete is unrecoverable**. A modal doesn't change that — it just adds a step in front of the same cliff.

On the ladder in the skill, a confirmation dialog is rung 2 (*Warning*) on paper and closer to rung 0 in practice: a dialog users meet routinely stops being a decision point and starts being a reflex. And "Are you sure?" specifically asks about the user's **resolve**, which was never the thing in doubt — they meant to click, they just misjudged which workspace or what it took with it.

## The device that actually closes it

**Soft-delete + a trash with retention, and an "Undo" toast on the action.** That's rung 1 (*Control*): the mistake becomes impossible to make *permanent*, so it needs no gate at all.

| | Now | With the device |
|---|---|---|
| User deletes wrong workspace | gone, emails support | clicks Undo in the toast |
| Notices next day | you restore from backup | they restore from Trash themselves |
| Support load | panic ticket | ~zero |

Two supporting pieces, because the form is only half a device:

- **Type-to-confirm belongs on the *purge*, not the delete.** Deleting into trash is cheap and reversible — let it be one click. Emptying trash early is the irreversible one; that's where "type `acme-prod` to confirm" earns its friction.
- **Behind the screen:** make the delete endpoint idempotent (hazard M2 — a double-click or a retry shouldn't produce two deletions or a 500 that looks like failure), and make sure permission is *enforced server-side*, not just hidden in the UI.

If you keep a dialog anyway, it should name the object and the scale — "Delete **acme-prod** — 47 projects, 12 members. Recoverable for 30 days." — not assert permanence it doesn't have.

`★ Insight ─────────────────────────────────────`
- The reason undo beats confirm isn't UX taste — it's inspection placement. A dialog is a *successive check* (someone verifies after the intent forms); reversibility is *source inspection* (the error can't become a defect at all).
- Under-used because it's a **backend** change, not a UI one — which is exactly why teams reach for the modal instead.
`─────────────────────────────────────────────────`

## Where I need your call

This repo is the poka-yoke skills repo, so I don't have your workspace app in front of me. Point me at the delete handler and I'll build it. Four decisions shape the implementation and they're genuinely yours:

1. **Retention window** — 30 days is conventional; shorter if workspaces are heavy.
2. **Billing & seats during the grace period** — does a trashed workspace still consume seats? (Charging for a deleted thing generates its own support tickets; not charging makes restore complicated.)
3. **Slug reuse** — can someone claim `acme-prod` while the old one is in trash? Blocking it is safer; allowing it is friendlier.
4. **Who can restore** — the deleter, any admin, or support only?

Give me those four and your stack, and I'll write the migration, the handler, and the undo toast.