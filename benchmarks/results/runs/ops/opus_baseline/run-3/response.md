Short answer: merge the code change, hold the `DROP`. Friday isn't the problem — the problem is that one deploy contains both a destructive schema change and the code that depends on it, and that combination has no rollback.

**What's irreversible, and what restores it?** `DROP COLUMN legacy_email`. Nothing restores it. Not `git revert`, not a redeploy. The only path back is a point-in-time restore of the whole database, which means losing every write since the drop. If you haven't rehearsed that restore recently, treat the data as unbacked.

**What breaks during the rollout window?** Deploys aren't atomic, so ordering decides whether you have an outage. If the migration lands before the last old pod drains, every request hitting those three paths errors until rollout finishes. Separately, `DROP COLUMN` takes an `ACCESS EXCLUSIVE` lock — it's metadata-only and fast, but it queues behind any long-running transaction and blocks all reads on the table while it waits.

**Can the irreversible part ship separately?** Yes, and it should:

- **PR A (today, safe):** code stops reading `legacy_email`. Fully reversible — rollback is a redeploy. Merge and ship this afternoon.
- **PR B (Tuesday):** the `DROP`, after PR A has baked long enough to prove nothing else touches the column.

That gap matters more than it sounds. "Three places in the code" is what grep found. Grep doesn't find `SELECT *`, ORM serializers that enumerate columns at runtime, raw SQL in a reporting job, a BI dashboard, a downstream ETL job, or another service pointed at the same database. Before dropping, confirm from the database side — `pg_stat_statements` or query logs filtered for the column name over a full week, so weekly batch jobs are in the sample.

**If it goes wrong, who's around?** Rolling back PR A is two minutes and any one person can do it. Recovering from a bad `DROP` is a multi-hour lossy restore needing someone with prod credentials — on a Friday evening.

★ Insight ─────────────────────────────────────
The reversible intermediate step here is a rename: `ALTER TABLE users RENAME COLUMN legacy_email TO zz_dead_legacy_email`. Anything still reading it fails loudly and immediately instead of silently, and the undo is a rename back — seconds, no data loss. It converts an irreversible test ("did we get all the readers?") into a reversible one. Drop it for real weeks later.
─────────────────────────────────────────────────

The device that makes this stick, rather than relying on you remembering it next time: a CI check that fails when a migration containing `DROP` or a destructive `ALTER` lands in the same diff as application code. Want me to write that check and its failing-case test? It's the kind of thing this repo argues should exist rather than being a line in a runbook.

One thing I'd want to confirm before you ship even PR A: is this repo the one with the migration, or is the PR elsewhere? I answered from your description rather than reading the diff.