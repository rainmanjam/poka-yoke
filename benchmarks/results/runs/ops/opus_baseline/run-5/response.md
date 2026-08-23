Using `poka-yoke:ops`. Short answer: **merge the code, don't ship the DROP** — and it isn't the Friday that's the problem.

The four things that matter here:

**1. What's irreversible, and what restores it?**
`DROP COLUMN legacy_email` destroys data. Nothing in your PR restores it. Rolling back the deploy rolls back the code; it does not bring the column back. Your only restore path is a point-in-time restore of the database — which means: has anyone actually run a PITR restore recently and timed it? If not, treat that data as unbacked.

**2. What breaks during the rollout window?**
Deploys aren't atomic. For a few minutes, old pods are still running the old code that reads `legacy_email`, against a schema where the column is gone. That window *is* the outage — not the change itself. Every read of that column throws until the last old instance drains.

**3. Can the irreversible part ship separately?**
Yes, and this is the whole fix. Split it:

- **Today:** merge and deploy only the three code changes that stop reading `legacy_email`. Fully reversible — revert reverts it.
- **Let it bake** a week or so, with the column still there. If you missed a reader, it errors while the data still exists and a revert still works.
- **Later, Monday-ish:** a separate PR containing only the `DROP`.

**4. If it goes wrong, who's around and how fast is rollback?**
That's the real Friday question — not superstition, staffing. Code-only deploy: rollback is a revert, minutes, safe alone at 5pm. Post-DROP: rollback is a database restore with someone paged on a weekend.

`★ Insight ─────────────────────────────────────`
"Three places in the code" is a grep result, and grep is rung-3 detection, not a control. It won't see raw SQL strings, `SELECT *` in an ORM, a BI/dashboard query, an ETL job, another service on the same DB, or a column name built dynamically. The bake period is what turns that assumption into evidence — the column is still there while you find out you were wrong.
`─────────────────────────────────────────────────`

Also worth checking on the DROP PR itself: is `legacy_email` referenced by an index, view, or FK? Postgres will refuse or cascade depending, and `DROP ... CASCADE` in a migration is a much bigger blast radius than it reads.

---

There's a device worth adding here, and the design choice is yours: a CI check that fails when a migration file containing `DROP`/destructive `ALTER` lands in the same PR as application code. The judgment call is the escape hatch — a PR label like `destructive-migration-approved`, a commit-message token, or no hatch at all (always two PRs). The label is flexible but gets rubber-stamped; no hatch is strict but occasionally wrong.

Want me to write that check? Tell me which escape hatch you want and where your migrations live, and I'll add it with a test that proves it goes red.