Using **poka-yoke:ux** (routed from the poka-yoke router — destructive action in an interface).

## Short answer: the modal is the weakest device on the list, and it's not where your problem is

Two facts in your message point somewhere else:

1. Users are emailing **support**, which means deletion is currently **unrecoverable** — that's the defect.
2. Support presumably has to say "sorry, it's gone" — so the panic is real, not just friction.

A modal doesn't fix either. On the ladder in the skill, a confirm dialog is **rung 2 (Warning)** at absolute best, and "Are you sure?" specifically is **rung 0** — it asks about the user's *resolve*, which was never in question. They meant to click delete; they were on the wrong workspace. Resolve isn't the failing check, identity is. And any dialog a user meets repeatedly gets click-through blindness, at which point it's friction on every legitimate delete and protection on none.

## What I'd build instead

**Soft-delete + 30-day trash + an undo toast.** That's **rung 1 (Control)** — the mistake stops being able to become a defect at all, because nothing is destroyed at click time.

| Layer | What it does | Rung |
|---|---|---|
| Soft-delete (`deleted_at`), hard-purge job at 30d | The panic email becomes a self-serve restore | Control |
| "Workspace *Acme Prod* deleted. **Undo**" toast, ~10s | Catches the wrong-workspace misclick in-session, zero friction | Control |
| Delete button out of the toolbar, into settings/menu, not styled as primary | Removes the misclick affordance | Control |

If you keep a dialog at all, it earns its place only by **naming the object and the scale** — "Delete **Acme Prod** — 47 projects, 1,204 files. Recoverable for 30 days." A count is real inspection. "This cannot be undone" is not — and once you have soft-delete, it'd also be a lie.

The honest cost: this is a backend change, not a UI change. That's exactly why teams reach for the modal instead. It's the cheaper thing, not the working thing.

`★ Insight ─────────────────────────────────────`
- The skill's rule is *undo beats confirm* — confirmation buys a decision point that degrades with repetition; reversibility buys one that doesn't.
- Reserve type-to-confirm (GitHub repo deletion) for **genuinely irreversible, high-blast-radius** actions. With a 30-day trash behind it, workspace delete no longer qualifies — using it anyway is theater and trains copy-paste.
`─────────────────────────────────────────────────`

## Three decisions I can't make for you

These shape the implementation and are genuinely yours:

1. **Billing and seats during the grace period** — does a trashed workspace keep consuming seats? (Charging for deleted things generates its own support emails; freeing seats makes restore fail when the org is full.)
2. **Slug/name reuse** — can someone create `acme-prod` while a deleted `acme-prod` sits in trash? Blocking is safer, confusing for the 99% who meant it.
3. **Who can restore** — the deleter, any admin, or support-only?

Tell me your stack and how you answer #1–3 and I'll write the schema change, the purge job, and the toast.