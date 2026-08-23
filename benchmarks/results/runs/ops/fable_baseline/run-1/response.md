Short answer: don't merge-and-deploy this as one step this afternoon. The "small change" framing is the hazard — a column drop is the one migration shape where green CI tells you almost nothing.

**Why CI green isn't evidence here**

1. **Deploy ordering.** If the migration runs before (or during) the rolling deploy, old app instances still reading `legacy_email` crash on every query touching that table — not just the three call sites you fixed, but any `SELECT *` / ORM model that still lists the column. If the migration runs after, the new code is fine but you've deployed nothing risky yet, so "tests pass" was never testing the dangerous moment.
2. **"Three places in the code" is only the places grep found.** Column references that don't live in your repo: reporting queries, dbt/ETL jobs, the data warehouse sync, ad-hoc dashboards, a Zapier/Retool, an index or view that depends on the column (Postgres will refuse the drop; MySQL will silently drop the index). CI doesn't exercise any of those.
3. **It's irreversible.** `DROP COLUMN` destroys data. A rollback of the deploy does not bring the column back. Your rollback path is "restore from backup," which is a Friday-night activity nobody wants.

**The mistake-proof shape (expand/contract)**

- **This afternoon (safe):** merge and deploy *only* the code change that stops reading the column. Don't drop anything. If you want a guard, have the ORM model mark it ignored/deprecated so new code can't reach it.
- **Monitor over the weekend/Monday:** DB query logs or `pg_stat_statements` for any statement still naming `legacy_email`. Zero hits for a few days is the real evidence the three call sites were all of them.
- **Next week, mid-week, morning:** run the `DROP COLUMN` as its own migration, after a verified backup, with someone around.

**Concrete checks before even the first step**

- `grep -r legacy_email` across *all* repos, SQL files, notebooks, BI configs — not just this one.
- Query the DB for dependent objects: views, indexes, triggers, generated columns, FKs.
- Confirm how your migrations run relative to the deploy (pre-deploy hook vs. manual), because that decides whether step 1 is genuinely harmless.

If you want, point me at the PR or the repo and I'll run the poka-yoke audit on the diff — the `poka-yoke:audit` skill is built for exactly this shape (migrations, silent fallbacks, unguarded destructive ops) and will turn the above into specific findings with devices, not a checklist to remember.