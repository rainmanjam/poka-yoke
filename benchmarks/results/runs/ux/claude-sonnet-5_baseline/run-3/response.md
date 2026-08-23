Not quite — a confirm modal is rung-0 theater here. This session already covered this exact question (see the earlier retro): users hitting a destructive workspace-delete a few times a day develop click-through blindness on "Are you sure?" dialogs, so it protects nobody while adding friction to everyone deleting on purpose. It won't stop the panic emails because the failure mode isn't "user didn't get asked," it's "the action was permanent."

What actually fixes it, strongest device first:

1. **Soft-delete + grace period (the real fix).** Delete just flips a `deletedAt`/status flag; workspace moves to trash, fully restorable for ~30 days, then hard-deleted by a job. This is a backend change, not a UI change, and it's why it's under-used — but it's the one that makes the panic emails go away, because now support's answer is "restored, done" instead of "sorry, gone."
2. **Immediate undo toast.** Delete fires right away, no dialog, with "Workspace deleted — Undo" for ~10s. Zero friction for people who meant it, full recovery for the fat-finger case.
3. **If you still want a gate for the genuinely-intended deletes**, use type-to-confirm (type the workspace name/slug) rather than a yes/no modal — it can't be dismissed reflexively the way "Are you sure?" can.

The confirm-modal instinct usually comes from treating the click as the failure point. It isn't — irreversibility is. Fix that and the click barely matters.

Earlier in this session I flagged three business decisions that block actually building this: what happens to billing/seats during the grace period, whether the workspace's URL slug gets released for reuse immediately or after the grace period, and who's allowed to trigger a restore. Want me to draft the soft-delete schema and restore endpoint, or do you want to settle those three first?