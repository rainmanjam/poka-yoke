Short answer: merge the code half, not the drop. Not because it's Friday — because of what "CI is green" actually proves.

**1. What's irreversible, and what restores it?**
`DROP COLUMN legacy_email`. The data is gone at that instant. What restores it is a point-in-time restore of the whole database to before the migration — not a revert, not a re-add. If nobody on your team has actually run a PITR restore recently, treat that data as gone with no restore path.

**2. What breaks during the rollout window?**
This is the part your test suite cannot see. CI proved *new code + new schema* works. It never ran *old code + new schema* — and that's the state that exists for real during every deploy, while old pods drain. Those three call sites throw `column does not exist` for every request they serve in that window. The change isn't risky; co-deploying it is an outage with a duration equal to your drain time.

**3. Can the irreversible part ship separately?**
Yes, and it's cheap. Two PRs:
- **Now:** the three code changes only. Nothing reads `legacy_email` anymore. Fully reversible — revert is a normal deploy.
- **Later (next week):** the `DROP`, alone, after you've confirmed from query logs that nothing touched the column for a few days.

Step two is where the "small change" framing is actually true. Right now the two halves are stapled together and the staple is the whole risk.

**4. If it goes wrong, how fast is rollback and who's around?**
This is what makes Friday matter here. Normally Friday is fine — you revert in ten minutes. But once the column is dropped, **revert makes it worse**: the old code you'd roll back to is the code that reads `legacy_email`. Your escape hatch is pointed at a wall. Recovery is a database restore, with a weekend on-call rotation.

`★ Insight ─────────────────────────────────────`
- Green CI on a schema PR is a *false instrument* — it tests the end state, never the mixed state that exists mid-rollout. It cannot fail for the thing most likely to break.
- Expand/contract exists to separate reversible steps from the one that isn't, so the irreversible one gets its own deploy and its own decision.
- A rename is a drop-plus-add in disguise; the same rule applies if this turns into one.
`─────────────────────────────────────────────────`

So: ship the code half this afternoon with confidence. Hold the `DROP` for Monday-to-Wednesday, alone.

Two things I can do if useful — say which:
1. **The device**, so this can't recur: a CI check that fails when a migration containing `DROP`/destructive `ALTER` lands in the same PR as application code. That's the thing that would have caught this without anyone remembering to look.
2. Split the PR for you — if you point me at the repo, I'll separate the code changes from the migration.