A confirmation modal is the weakest rung on the mistake-proofing ladder — users click "Yes" reflexively without reading. If they're emailing support *in a panic*, the actual need is **reversibility**, not a speed bump.

Better approach:

1. **Soft-delete + trash** — workspace moves to a "Recently Deleted" folder, auto-purged after 30 days
2. **Undo toast** — "Workspace deleted. [Undo]" visible for 10 seconds after the action
3. **Type-to-confirm** (optional, for high-value workspaces) — require typing the workspace name

This eliminates support tickets entirely because users can self-recover. The modal makes them feel bad about a mistake they can't fix; soft-delete means there's no mistake to make.

Want me to sketch the implementation, or audit the current delete code path first?