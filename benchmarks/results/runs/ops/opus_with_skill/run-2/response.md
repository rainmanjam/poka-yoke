Using `poka-yoke:ops` — the router sends a column drop + deploy question there.

**Short answer: ship half of it this afternoon, not the whole thing.** The problem isn't Friday, it's that the PR staples a reversible change to an irreversible one.

## The four questions

**1. What's irreversible, and what restores it?** `DROP COLUMN legacy_email`. Nothing in your deploy restores it. Recovery is a PITR/backup restore — either roll the whole DB back (losing every write since) or restore a copy to a scratch instance and write a backfill you don't have yet. If nobody has actually restored that backup recently, treat the data as unbacked when you size this.

**2. What breaks during the rollout window?** Deploys aren't atomic. For the minutes it takes to cycle instances, old code runs against the new schema and every query touching `legacy_email` fails with "column does not exist." That window *is* the outage — not the drop itself. CI is green because no test runs old code against new schema.

**3. Can the irreversible part ship separately?** Yes, and this is the whole answer. Your PR is expand/contract steps 4 and 5 fused. Step 4 (stop reading it) is fully reversible; step 5 (drop) is not. Split them.

**4. How fast is rollback, and who's around?** A code revert is two minutes — fine on a Friday. But *once the migration has run, the revert is broken*: reverting reintroduces code that reads a column that no longer exists. You'd be shipping a change whose rollback path is destroyed by the change itself, into a weekend.

## Also: "three places" is a grep, not a measurement

CI green proves the tests you have pass. It doesn't cover: `SELECT *` / ORM models that map the column, raw SQL in BI dashboards, other services on the same database, monthly cron jobs no test exercises, warehouse ETL, views or indexes referencing it. Don't grep — measure. Check `pg_stat_statements` (or equivalent) for the column name over a window that includes at least one monthly job cycle.

## What I'd do

| When | Action | Rung |
|---|---|---|
| This afternoon | Ship the code-only PR — remove the three reads, leave the column | **Control** — nothing can break in the window, the column still exists; revert is a redeploy |
| Next week | Confirm zero reads over a full job cycle | Warning |
| Weekday morning | `CREATE TABLE legacy_email_archive AS SELECT id, legacy_email FROM …`, then drop, own deploy | Turns irreversible into reversible for one table copy |

The archive step is the highest-leverage move here: one cheap copy collapses the cost of being wrong from "restore the database" to "run one UPDATE."

`★ Insight ─────────────────────────────────────`
- Rollback safety isn't a property of a change, it's a property of the *pair* of changes — this PR's revert is broken by its own migration, which is invisible when you review the diff as a unit.
- "Friday" is a proxy people use for "recovery needs humans who aren't here." Ask the real question and the rule dissolves: fast-revert changes are fine Friday, restore-path changes aren't fine Tuesday either.
`─────────────────────────────────────────────────`

Two things I can do next, say the word:

1. **Write the CI gate** (`assets/devices/github-actions/` has a migration-safety workflow) that blocks `DROP`/`TRUNCATE`/`ALTER … DROP` in a migration unless the PR carries an explicit label — so the next fused PR can't merge. I'd break it on purpose and show you it going red before I call it done.
2. **Look at the actual diff** — I've answered from your description; if you point me at the branch I'll check whether those three sites are really all of them.