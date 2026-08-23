Using **poka-yoke:ops** (routed from the poka-yoke router — this is a migration/deploy question).

## The four things you need before shipping

**1. What's irreversible, and what restores it?**
The `DROP COLUMN`. Nothing restores it. Not a revert, not a redeploy — the data is gone the instant the migration runs. The only restore path is a PITR restore of the whole database to a pre-drop timestamp, then extracting one column and re-merging it, which costs hours and loses everything written since. CI green tells you nothing about this; no test exercises "the column is gone and I needed it."

**2. What breaks during the rollout window?**
Deploys aren't atomic. For the minutes between the migration running and the last old pod draining, old code is still `SELECT`ing `legacy_email` against a schema that no longer has it — every request on those paths 500s. Worse: your rollback is now the broken artifact. Reverting the deploy reintroduces code that reads a dropped column.

**3. Can the irreversible part ship separately?**
Yes, and it should. This PR is one reversible change and one irreversible change stapled together:

- **Deploy A (today, Friday, fine):** the code-only removal of the three reads. Nothing depends on it, reverts in one deploy, zero data risk.
- **Deploy B (Monday/Tuesday morning):** the `DROP`, alone, once nothing has touched the column for a few days.

Between them, do the verification CI can't do: grep *every* repo, not just this one — analytics jobs, dbt models, BI/Looker queries, one-off scripts, exports, the data warehouse ingest. Then check `pg_stat_statements` (or query logs) for a week for any read of that column. "Three places in the code" is a count you got from grep, not from a device.

**4. Rollback speed vs. who's around.**
Friday isn't superstition — it's staffing. Deploy A reverts in minutes, so ship it. Deploy B has no rollback at any speed, which is exactly why it shouldn't land when the people who'd do a restore are heading out.

## The device that makes the drop reversible

Before Deploy B, rename instead of dropping:

```sql
ALTER TABLE users RENAME COLUMN legacy_email TO zz_dropped_legacy_email_20260901;
```

Any hidden reader you missed fails loudly and immediately, and undoing it is one command with the data intact. Drop it for real two weeks later. That converts an unrecoverable operation into a reversible one — the highest-leverage move available here, and it costs one line.

## The device that stops the next one

A CI check that fails any PR containing `DROP COLUMN`/`DROP TABLE`/`TRUNCATE` in a migration *alongside* application code changes — Control, not a checklist item. Want me to write it? I'd need to know your CI (GitHub Actions?) and migration directory.