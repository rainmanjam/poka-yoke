Grep only turns up benchmark fixtures — `legacy_email` isn't in this repo, so I'm answering on the shape of the change, not on your actual diff. Adjust if any of my assumptions are wrong.

## Short answer

Merge it. Don't deploy it as one unit — not because it's Friday, but because it's two changes stapled together and only one of them is reversible.

## The four things that matter

**1. What's irreversible, and what restores it?** The `DROP`. Nothing restores it cheaply. Recovering those values means a point-in-time restore of the whole database into a side instance and re-extracting one column — hours, and it needs someone who has done it before. If you've never actually run that restore, treat the data as unbacked when you size the risk.

**2. What breaks during the rollout window?** Deploys aren't atomic. For the minutes your old pods coexist with the new schema, every request hitting those three readers on an old pod errors. Worse: **you cannot roll back.** The revert-and-redeploy escape hatch depends on the old code's column still existing. Once it's dropped, your only path is forward through a hotfix — at 5pm on a Friday.

**3. Can the irreversible part ship separately?** Yes, and this is the whole fix:

- **PR A** — code stops reading `legacy_email`. Fully reversible, deployable this afternoon, roll back in two minutes if anything smells.
- **PR B** — the `DROP`, next week, after A has been live through a full weekly traffic cycle including whatever batch jobs only run on Sundays.

**4. Who's around, and how fast is rollback?** That's the real Friday question. A change that reverts in two minutes is fine on a Friday. This one's recovery path is a DB restore with your team offline until Monday.

## About "CI is green"

CI green proves your *tests* don't read that column. It doesn't prove nothing does. What a grep plus a test suite structurally cannot see:

- raw SQL or string-built queries
- `SELECT *` into a dict/row object, accessed by key
- analytics, BI, dbt models, ETL exports — usually a different repo entirely
- other services sharing the database
- queued jobs holding serialized payloads written by old code
- read replicas and admin tooling

Also: "three places" is a suspiciously round number for a legacy column. Did that count include the ORM model definition, serializers, and fixtures, or just call sites?

**The device that turns belief into evidence:** before PR B, query `pg_stat_statements` (or your engine's equivalent / query logs) for any statement referencing `legacy_email` over the last 30 days. That's a measurement. Grep + CI is an argument.

## The cheap middle rung

If you want the column gone sooner: in PR B, `ALTER TABLE ... RENAME COLUMN legacy_email TO legacy_email_deprecated_20260822` instead of dropping. Anything still reading it breaks immediately and loudly — and the rename reverses in one second. Drop for real 30 days later. You get the flush-out effect without the one-way door.

`★ Insight ─────────────────────────────────────`
The expand/contract sequence (add → backfill → dual-write → switch reads → contract) exists so that every step but the last is reversible. Your PR is doing steps 4 and 5 in one deploy; splitting them is the entire discipline.
The strongest signal that a change needs splitting isn't its size — it's whether `git revert` is a sufficient rollback. Here it isn't, and a one-line diff can fail that test as easily as a thousand-line one.
`─────────────────────────────────────────────────`

Want me to draft the CI check that blocks destructive DDL from landing in the same commit as application code? That's the device that makes this stick after everyone forgets this conversation.