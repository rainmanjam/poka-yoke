I'd push back on the confirmation modal — here's why:

**The problem isn't that users don't *notice* they're deleting, it's that they can't *undo* after they do.**

A modal is detection-level poka-yoke (the weakest rung). Users develop muscle memory to click "OK" on modals, so you'll still get panic emails — just fewer of them. And those users are still stuck waiting for support.

**Better approach: soft-delete + trash**

1. **Delete → Archive** — clicking "delete" marks the workspace as archived, doesn't destroy data
2. **Trash view** — dedicated UI to browse/restore deleted workspaces  
3. **30-day retention** — workspaces auto-purge after 30 days (or whatever fits your economics)
4. **Undo toast** — "Workspace deleted. **Undo**" appears immediately after delete action
5. **Self-serve recovery** — users restore their own workspaces, no support ticket

This eliminates the entire support cycle. The "panic email" scenario goes to zero because users can fix it themselves in 5 seconds.

**★ Insight ─────────────────────────────────────**  
• Poka-yoke hierarchy: Elimination > Replacement > Facilitation > Detection > Mitigation  
• Modals are detection — they *tell you* about the mistake but don't prevent consequences  
• Soft-delete is replacement — it makes the destructive action reversible by design  
• Every "are you sure?" modal is a design admission that the consequence is too harsh  
**─────────────────────────────────────────────────**

**If you must keep hard-delete**, at least make the modal harder to habituation-click:
- Require typing the workspace name (breaks muscle memory)
- Show what will be lost (project count, last activity, team members)
- Make "Cancel" the default/escape-key action

Want me to sketch out the soft-delete schema design?