Not really — an "are you sure?" modal is the weakest device on the ladder for this problem, and per session memory I flagged this exact same tradeoff earlier today.

**Why it won't fix the panic-emails:** a generic confirm dialog is rung 0 — it relies on the user reading it. People who habitually click through dialogs (which is most people, most of the time) will click through this one too. It adds friction to every legitimate deletion without stopping the accidental one, and it does nothing for the actual failure mode you're describing: the workspace is *gone* and support has no way to get it back.

**What actually solves "panic email to support":**
1. **Soft-delete with a grace period** (strongest fix) — deleting marks the workspace for purge in ~30 days instead of removing it immediately. This is the real answer, and it's a backend change, not a modal.
2. **Grace-period undo toast** — "Workspace deleted. Undo" for ~10 seconds, no friction on the happy path.
3. If you want a confirm step at all, make it **proportional**: type-to-confirm (workspace name) rather than "Are you sure?" — reserve that for genuinely one-way actions.

The reason this beats a modal: the support emails happen *after* the user already clicked delete and regretted it. A confirm dialog only helps in the narrow window before the click; it does nothing once they've already confirmed (which they will, reflexively). Soft-delete + restore means support can just click "restore" instead of escalating to engineering.

Three business decisions block the soft-delete design (per earlier analysis this session): what happens to billing/seats during the grace period, whether the subdomain/slug gets freed immediately or held for the grace period, and who can trigger a restore (owner only, or any admin).

Want me to spec out the soft-delete schema + restore flow, or do you want to keep it simpler for now (undo toast only, hard-delete after)?