Using **poka-yoke:ops** (routed from the poka-yoke router — this is a migration + deploy question).

I haven't seen the PR, so this is from your description: a `DROP COLUMN` and its dependent code changes in one deploy.

**Short answer: the code half can go Friday. The `DROP` should not — not because it's Friday, but because it's the one step with no revert.**

The problem isn't size. It's that this PR staples a reversible change (three call sites stop reading a column) to an irreversible one (the column ceases to exist), and the reversible half is what CI proved.

## The four questions

**1. What's irreversible, and what restores it?**
`DROP COLUMN legacy_email`. Reverting the PR re-adds an *empty* column — the values are gone. The only real restore is point-in-time recovery: snapshot to a side instance, extract, backfill. If nobody has actually run that restore recently, treat the data as unbacked when you size the risk.

**2. What breaks during the rollout window?**
This is the part CI cannot have tested. Deploys aren't atomic. Once the migration runs, old instances still holding `SELECT ... legacy_email` (or `SELECT *` through an ORM) error on every request they serve until they're replaced. CI tested *new code against new schema*. Nobody tested *old code against new schema* — and that combination is guaranteed to exist for the length of the rollout.

Worse: it also poisons your rollback. After the `DROP` lands, "just revert the deploy" reintroduces code that queries a column that no longer exists. Your escape hatch is gone at exactly the moment you'd reach for it.

**3. Can the irreversible part ship separately?**
Yes, and this is the whole recommendation:

- **Deploy A (Friday is fine):** code only. Stop reading `legacy_email`. Column stays. Fully reversible — revert reverts.
- **Deploy B (next week, morning):** the `DROP`, alone, after A has soaked and you've confirmed zero reads.

**4. Rollback speed and who's around?**
Deploy A reverts in minutes → Friday afternoon is genuinely fine. Deploy B has no fast revert at all → it wants people awake, which Friday afternoon isn't.

## One thing to check before Deploy B

"Three places in the code" is a grep result. A grep doesn't see: raw SQL strings, `SELECT *` serializers, dbt/BI models, Looker or Metabase saved queries, CSV exports, ETL into the warehouse, admin tooling, or another service reading your replica. Before the drop, check actual query traffic — `pg_stat_statements` filtered for `legacy_email` over your full retention window is the cheap version.

## The device, so this doesn't recur

Rung 1 (Control): a CI check that fails any PR whose migration contains `DROP`, `TRUNCATE`, or `ALTER ... DROP` unless the PR carries an explicit approval label. That makes "destructive migration rides along with app code" not a judgment call anyone has to remember on a Friday — it's just not mergeable. The `guardrails` mode in this repo covers the gate itself if you want it built.

Want me to write that CI check?