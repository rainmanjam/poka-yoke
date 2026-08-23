Using `poka-yoke:ops` — the router sends a column drop + deploy here. I'm answering from your description; I haven't seen the PR.

## The four questions

**1. What's irreversible, and what restores it?**
The `DROP COLUMN` is. The code changes revert in a `git revert`; the column does not come back with them. What restores it is a restore from backup or PITR — which brings back the *data*, not just the column, and a full restore rolls back everything else too. If your only answer is "we'd restore from backup," check when that backup was last actually restored. An untested backup is a belief, not a device. If nobody has restored it, treat the data as gone.

**2. What breaks during the rollout window?**
This is the part CI cannot see, and it's usually the real outage. Deploys are not atomic. If the migration runs before every old instance is drained — and it typically does — old code selects `legacy_email` against a schema where it no longer exists. Postgres doesn't return null there; it errors the whole query. Depending on where those three read sites are, that's 500s on live traffic for the length of the rollout, not a degraded field.

Green CI is expected here and tells you nothing about it: tests run one code version against one schema version. The failure mode is old-code-vs-new-schema, a combination nothing in your pipeline ever ran.

**3. Can the irreversible part ship separately?**
Yes, and it's the whole recommendation. Your PR is a reversible change and an irreversible one stapled together:

- **Deploy A (today):** the three code changes only. Nothing reads `legacy_email` anymore; the column sits there unused. Fully reversible — revert the deploy and you're back.
- **Deploy B (next week):** the `DROP COLUMN`, alone, once you've confirmed nothing touches it. Confirm with `pg_stat_statements` or query logs over a few days, not by grepping — ORMs with `SELECT *`, analytics jobs, dbt models, cron scripts, and read replicas don't show up in a repo grep, and "three places in the code" is exactly the count that turns out to be four.

**4. If it goes wrong, who's around and how fast is rollback?**
Friday isn't superstition, it's staffing. Deploy A reverts in minutes, so ship it Friday afternoon without concern. Deploy B's failure mode needs someone who can run a restore — if that person is offline until Monday, the drop waits.

## The device

The reason this reached you as one PR is that nothing stopped it being one. The fix is a CI gate: any migration containing `DROP`, `TRUNCATE`, or `ALTER ... DROP` fails unless the PR carries an explicit `destructive-migration` label. That's rung 1, Control — the co-deploy becomes unmergeable rather than discouraged. Want me to write that check?