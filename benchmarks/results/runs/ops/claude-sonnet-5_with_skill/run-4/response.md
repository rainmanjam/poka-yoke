Using **poka-yoke:ops** (this is a "can I ship this on Friday" / migration-drops-a-column case) to check the risk before you answer yourself.

The core issue: dropping a column bundles a *reversible* change (removing the three read sites) with an *irreversible* one (the `DROP COLUMN`), and ships both together on a Friday afternoon. Walking through the four questions this mode requires before any recommendation:

1. **What's irreversible, and what restores it?** The `DROP COLUMN` itself. Nothing in-database restores it — only a full snapshot/backup restore, which also rolls back everything else written since that snapshot. If you haven't checked when this table's backup was last *restored* (not just taken), treat it as unrestorable for planning purposes.

2. **What breaks during the rollout window?** Deploys aren't atomic. If the column drops before every old pod/instance has cycled to the new code, any straggler still reading `legacy_email` errors immediately. Conversely, if you need to roll the *code* back after the migration has run, the old code can't run — the column it expects is gone. That converts a normal "revert in twenty minutes" into "code revert is now unavailable" the moment the migration lands.

3. **Can the irreversible part ship separately?** Yes, and it should. This is the textbook contract step of expand/contract: the safe order is (a) ship the code change removing the three reads, alone, (b) bake it in production for a bit — confirm via logs/error tracking that nothing still touches the column, (c) drop the column in its *own* migration afterward.

4. **If it goes wrong, who's around and how fast is rollback?** This is the actual "Friday" question — not superstition, staffing. Reverting the code deploy is fast. Reverting a completed `DROP COLUMN` is a backup restore, likely hours, with fewer people around Friday evening/weekend to run it.

**Recommendation:** don't merge code-removal and column-drop as one Friday-afternoon change. Split them — ship the read-site removal now (that part's genuinely low-risk and revertible), then drop the column as a separate migration early next week when the team's around, after confirming a recent backup restores cleanly. That's Control-rung (the irreversible step can't land at a bad time because it's not coupled to this deploy) rather than just being careful.