No — split it. Right now the PR bundles a reversible change (removing the three code reads) with an irreversible one (dropping the column), and that's the combination to avoid regardless of the day.

1. **What's irreversible, what restores it?** The `DROP COLUMN` itself. Once it's gone, the only restore path is a database backup/point-in-time-recovery — and that's a full restore, not a quick fix, and only works if it's actually been tested recently.
2. **What breaks during rollout?** Deploys aren't atomic. If any old pod/instance is still running while the column is gone (or vice versa — new code deployed before the column drop, briefly reading a column that's about to disappear), you get errors in that window. Since you're removing the three read sites, the real risk is sequencing: if the column drop reaches the DB before every reader is confirmed off it, requests in flight fail.
3. **Can the irreversible part ship separately? Yes, and it should:**
   - **Deploy 1 (today, Friday-safe):** ship just the code changes removing the three reads. Fully reversible — a revert PR undoes it in minutes.
   - **Verify:** confirm nothing else reads the column — grep the org, not just this repo, and check query logs/APM for any live reads over the last 1-2 weeks (ORMs, reporting jobs, and other services are the usual surprises).
   - **Deploy 2 (separate, non-Friday):** the `DROP COLUMN` migration, once you're confident.
4. **If it goes wrong, who's around?** That question only matters for deploy 2. Deploy 1 (code-only) is safe for a Friday afternoon since rollback is a normal git revert.

So: merge and deploy the code-only change today, hold the `DROP COLUMN` for a day with people around, after you've confirmed via logs/grep that nothing outside this PR still touches `legacy_email`.

One device worth adding regardless: a CI check that blocks `DROP`/destructive `ALTER` statements from landing in the same PR as application code, so this split becomes structural instead of something to remember each time.