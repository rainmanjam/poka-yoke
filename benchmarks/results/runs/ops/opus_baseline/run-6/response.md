Note: this repo has no `legacy_email` outside benchmark fixtures, so I'm answering from the description, not your diff.

**Short answer: merge it, but split it. Deploy the code half this afternoon; hold the `DROP` until Monday.**

The problem isn't Friday. It's that the PR staples a reversible change to an irreversible one.

**1. What's irreversible, and what restores it?** The `DROP`. Nothing in the PR restores it — not a revert, not a redeploy. The only restore path is a database point-in-time restore, which brings back the whole database, not the column, and loses everything written since. Treat the data in that column as gone the moment the migration runs.

**2. What breaks during the rollout window?** Deploys aren't atomic. Whichever order you pick, there's a window where old instances `SELECT legacy_email` against a schema that no longer has it — errors on every request through those three paths. Worse: the standard Friday escape hatch is disabled. Revert the deploy and you've restored code that reads a column that doesn't exist. You'd be rolling *forward* under pressure at 6pm.

**3. Can the irreversible part ship separately?** Yes, and that's the fix. This is the "contract" step of expand/contract, and it belongs in its own deploy:

- **Today:** merge the code change — the three call sites stop reading `legacy_email`. Fully revertible, safe to ship Friday.
- **Next week:** separate PR, just the migration, after the code has soaked in prod and you've confirmed nothing reads the column.

**4. Rollback speed and staffing?** Code-only: minutes, and one person can do it. With the `DROP`: hours, needs someone with restore access, and Friday evening is when that person is least likely to be reachable. That asymmetry is the whole argument.

**On "three places":** CI green proves the three you found still compile. It doesn't prove there were only three. Things that pass CI and still break in prod — raw SQL strings, `SELECT *` hydrating an ORM model, the model/schema definition itself, analytics and BI queries, warehouse ETL, another service on the same database, admin tooling, seeds and fixtures. Before the `DROP` lands, confirm nothing wrote to the column in the last N days, and confirm the data is genuinely redundant with wherever it moved.

`★ Insight ─────────────────────────────────────`
- The migration's *lock* probably isn't your risk — in Postgres `DROP COLUMN` is metadata-only and near-instant. Reversibility is the risk. Easy to conflate "fast" with "safe."
- Splitting the deploy is what makes step 5 gateable at all. When contract has its own PR, a CI rule can inspect it in isolation.
`─────────────────────────────────────────────────`

The device that stops you re-litigating this: a CI check blocking destructive DDL in the same change as application code. Want me to write one for your repo?