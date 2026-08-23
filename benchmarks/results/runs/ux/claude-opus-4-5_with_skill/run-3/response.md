Honest answer: **an "are you sure?" modal is the weakest poka-yoke for this problem** — it will become click-through muscle memory within a week and the panicked emails will resume.

`★ Insight ─────────────────────────────────────`
Shingo's ladder ranks devices by how hard they make a mistake. A generic confirmation dialog sits at rung 2 (warning), but barely — users develop *click-through blindness* and dismiss it reflexively. The fact that users are deleting workspaces *and then panicking* tells you something: the action felt reversible until it wasn't. The fix should make it actually reversible.
`─────────────────────────────────────────────────`

## The preference order for destructive actions

| Rank | Device | Why it works |
|------|--------|--------------|
| **1** | **Soft-delete + trash** | Mistake has no permanent consequence. User can self-recover. Zero support tickets. |
| **2** | **Grace-period undo** | "Workspace deleted. [Undo]" toast for 10s. No friction on happy path, full recovery on mistake. |
| **3** | **Type-to-confirm** | Requires typing the workspace name — can't be done reflexively. GitHub uses this for repo deletion. |
| **4** | Confirmation dialog | "Are you sure?" becomes invisible. Only works if it names the *exact* thing and count being destroyed. |

## My recommendation

**Implement soft-delete + a 30-day trash retention.** The modal becomes unnecessary — users can recover their own workspaces, and you can add a "Restore from Trash" screen. Support ticket volume for accidental deletions goes to zero.

If soft-delete is too expensive right now, **grace-period undo** (a toast with an Undo button for ~10 seconds) is the next best thing — it's a frontend-only change that still prevents most panics.

The "are you sure?" modal only works if you're blocking on it as a temporary measure while building real reversibility. Want me to sketch the soft-delete approach, or is there a constraint that makes reversibility hard here?