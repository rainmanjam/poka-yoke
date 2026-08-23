A confirmation modal is the weakest rung on the poka-yoke ladder — users click through them on autopilot, and it won't stop the panicked support emails.

`★ Insight ─────────────────────────────────────`
**Poka-yoke control hierarchy** (strongest → weakest):
1. **Elimination** — remove the hazard entirely
2. **Substitution** — replace with something safer
3. **Prevention** — make the error impossible
4. **Detection** — catch it before harm ← confirmation modals live here
5. **Mitigation** — reduce the damage after the fact
`─────────────────────────────────────────────────`

**Better approach: make deletion reversible**

| Control | Implementation |
|---------|----------------|
| Soft-delete | Mark as deleted, don't purge immediately |
| Trash folder | Users can self-recover for 30 days |
| Undo toast | "Workspace deleted — Undo" for 10 seconds |
| Hard-delete friction | Require typing workspace name to permanently purge |

This eliminates the support emails because users can fix it themselves. The modal stays optional as a speed bump, but it's no longer load-bearing.

Want me to audit the current delete code path to see what's involved in adding soft-delete?