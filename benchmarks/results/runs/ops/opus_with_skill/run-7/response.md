I read the router and it sent me to `ops` (a change that drops a column). Note: `legacy_email` only appears here in benchmark fixtures, so I'm answering from your description, not from your PR.

Short answer: **merge and deploy the code half this afternoon. Don't run the DROP.** The problem isn't Friday — it's that the PR staples a reversible change to an irreversible one.

The four questions `ops` says to answer first:

**1. What's irreversible, and what restores it?**
The `DROP COLUMN`. Nothing in the PR restores it. `git revert` brings back the code, not the bytes — those are gone the moment the migration runs. Your only restore path is a backup, and per the skill, a backup nobody has restored is a belief, not a device. If you don't know when that database was last *restored* (not last backed up), treat the data as unbacked.

**2. What breaks during the rollout window?**
Deploys aren't atomic. During the rolling restart, old pods are still running `SELECT ... legacy_email` against a schema where it no longer exists. Every request through those three paths 500s until the last old instance drains. That window *is* the outage — not the change.

Worse: once the migration has run, rollback is no longer available. Rolling back the code reintroduces the three readers against a dropped column. You'd be forward-only at 5pm Friday.

**3. Can the irreversible part ship separately?**
Yes, and this is the whole recommendation. You're at step 5 of expand/contract. Steps 1–4 are reversible; step 5 gets its own deploy precisely because it isn't. Ship the code-only PR today, let it bake through a full traffic cycle, drop the column Tuesday.

**4. Who's around, and how fast is rollback?**
Code-only deploy: reverts in minutes, fine on a Friday. The drop: needs a restore, two people, and hours. The skill's line is that timing is about staffing and recovery speed, not superstition — and by that test the code half passes and the drop fails.

`★ Insight ─────────────────────────────────────`
"CI is green" proves nothing about the column. CI tests *this repo*; a column is read by everything with database credentials. Before the drop, check: ORM `SELECT *` / row-to-struct mappers that never name the column, dbt models and warehouse ETL, BI dashboards, read replicas, admin panels, other services, and raw SQL in old migrations.
`─────────────────────────────────────────────────`

**The device** (rung 1, Control): a CI check that fails any PR whose migrations contain `DROP`, `TRUNCATE`, or `ALTER ... DROP` unless the PR carries an explicit approval label. That makes "code and drop in one PR" unmergeable rather than something you have to notice. The `guardrails` skill has the gate itself — want me to draft it?