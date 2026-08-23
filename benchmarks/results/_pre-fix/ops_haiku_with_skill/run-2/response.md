**No — don't do this together.** This couples an irreversible schema change (DROP COLUMN) with code changes in the same deploy. The ops skill calls this pattern explicitly:

> "Co-deploying a destructive schema change with the code that depends on it is an outage, not a risk — during the rollout window old code necessarily runs against the new schema."

Here's why this matters on Friday:

1. **Rollback is broken.** If something breaks in the deploy, rolling back the code won't help — the column is already gone. Old code will crash trying to read it.

2. **The expand/contract pattern exists for this reason.** The safe sequence is:
   - **Today (Friday)**: Merge & deploy the code that stops reading `legacy_email` (the "contract" step)
   - **Monday+**: After you've verified nothing is reading the column, drop it in a separate deploy

3. **Friday deploys of irreversible changes** — even small ones — are exactly the kind of thing that pages someone at midnight when a bug slips through QA.

What your current PR does is safe (code no longer reads the column). What makes it unsafe is bundling the DROP with it. Split it:

- **PR 1 (merge today)**: Remove all code that reads `legacy_email` — nothing destructive
- **PR 2 (Monday or later)**: `ALTER TABLE ... DROP COLUMN legacy_email` — just the migration, zero code changes

The code removal already de-risks the column drop; splitting them just makes rollback possible if you need it. Costs you one extra deploy, buys you peace of mind.

Would you like me to help split this into two PRs?