Using `poka-yoke:poka-yoke` → routed to `poka-yoke:ux` (users deleting the wrong thing / adding a confirmation).

**Short answer: no — that's the weakest device available here, and the panic emails are the evidence.**

An "Are you sure?" modal asks about the user's *resolve*. Their resolve was never the problem: they meant to click something, they were wrong about *which* thing or about what it took with it. A dialog they see repeatedly stops being a decision point — click-through blindness sets in and it protects nobody while taxing every legitimate delete. On the ladder in the skill it's rung 0 dressed as rung 2.

The real signal is that people email support afterward: they're asking you to *undo* it. That means the fix is recoverability, not a gate.

### What I'd build instead

**Rung 1 (Control) — soft delete + trash + undo toast.** Deleting sets `deleted_at`; the workspace drops out of every query but the rows stay. A purge job hard-deletes after 30 days. On click: delete immediately, show `Workspace "Acme Prod" deleted. Undo` for ~8 seconds, and keep it listed under Trash for the rest of the window. No dialog at all. Zero friction on the happy path, full recovery on the mistake, and support's inbox empties out because users fix it themselves.

It's a backend change, not a UI change — which is exactly why it's under-used and why the modal is tempting.

**If you can't ship the backend change this week**, the fallback is a dialog that does fixed-value inspection rather than asking about resolve: name the workspace, state the scale (`Delete "Acme Prod" — 14 projects, 1,204 files, 8 members?`), be honest about reversibility, and label the button `Delete workspace` not `OK`. That's rung 2, and say out loud it's a stopgap for the trash.

Skip type-to-confirm unless a workspace delete is genuinely unrecoverable — used broadly it becomes copy-paste theater.

**The server half:** a modal in front of a non-idempotent, unscoped endpoint is half a device. `DELETE /workspaces/:id` needs tenant scoping and idempotency regardless of what the UI does.

`★ Insight ─────────────────────────────────────`
- Confirmation is *informative inspection* — it happens at the moment of error. Soft delete is *source inspection*: it removes the irreversibility that makes the error a defect at all.
- Undo is cheaper than it looks. The hard part isn't the `deleted_at` column, it's every read path remembering to filter — so make the filter a scoped repository/RLS policy, not a `WHERE` clause each caller must recall.
`─────────────────────────────────────────────────`

### Three decisions that shape this — your call, not mine

1. **Billing and seats during the grace window** — does a trashed workspace still consume seats/charge? (Free = abuse vector; charged = angry tickets.)
2. **Slug reuse** — is `acme-prod` claimable while the old one sits in trash? If yes, restore needs a rename path.
3. **Who can restore** — only the deleter, any admin, or support?

Tell me the stack and answers to those and I'll write the migration, the scoped read path, and the undo toast.