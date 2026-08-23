Using `poka-yoke:ux` (routed from the poka-yoke router) — it covers destructive actions and confirmation dialogs directly.

Short answer: the modal is the weakest device available here, and the panicked emails are evidence of that rather than an argument for it. Those users *meant* to click delete on something — they were confident. "Are you sure?" asks about resolve, and their resolve was never in question. They'd have clicked Yes.

The real defect isn't the missing prompt, it's that the delete is unrecoverable. Support can't fix it, so it becomes an email.

**The ladder for this, strongest first:**

1. **Soft-delete + restore window (Control).** Workspace goes to a deleted state, hard-purges after 30 days, self-serve restore in the UI. The mistake now has no permanent consequence and needs no gate at all. This is a backend change, which is exactly why teams reach for the modal instead — but it's the only option that actually closes the hazard, and it deletes the support queue rather than shrinking it.
2. **Grace-period undo (Control).** "Workspace deleted. Undo" toast for ~10s. Zero friction on the happy path. Good complement to #1, not a substitute — it doesn't help the user who realises tomorrow.
3. **Type the workspace name to confirm (Warning).** GitHub's repo-delete pattern. Can't be done reflexively. Worth having *alongside* soft-delete for the purge step, not instead of it.
4. **"Are you sure?" (rung 0).** Where you were headed. Trains click-through blindness and protects nobody.

If you ship a dialog at all, make it name the workspace, state the scale ("4 projects, 1,204 files, 12 members"), tell the truth about reversibility ("recoverable for 30 days"), and label the button "Delete workspace" — not "OK".

`★ Insight ─────────────────────────────────────`
A dialog stating a specific count is doing fixed-value inspection — it lets the user check a fact. A dialog asking about certainty checks nothing, which is why it degrades into reflex.
`─────────────────────────────────────────────────`

**The decision that's actually yours**, and it shapes the build: during the 30-day soft-delete window, what stays live? Billing (do you keep charging?), the subdomain/slug (released immediately or held?), API keys and webhooks (revoked or dormant?), and member access. Holding everything makes restore clean but leaves a paying zombie; releasing the slug makes restore partial. Which way do you want it?

Your session notes from 2026-08-21 mention a soft-delete retention design for workspaces — worth checking whether that's the same product before building it twice.