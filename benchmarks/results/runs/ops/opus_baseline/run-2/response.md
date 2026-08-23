Using **poka-yoke:ops** — this is a destructive migration co-deployed with the code that depends on it, which is the exact shape the skill exists for.

Short answer: **merge yes, deploy the code yes, deploy the `DROP` no.** Not because it's Friday — because the two halves are stapled together.

## The four things that matter

**1. What's irreversible, and what restores it?** `DROP COLUMN legacy_email`. Nothing restores it in place. Your only recovery is a point-in-time restore of the whole database to before the migration, which throws away every write since. Assume the data is gone the moment it commits.

**2. What breaks during the rollout window?** Deploys aren't atomic. Between the migration running and your last old pod draining, old code is selecting a column that no longer exists — those three call sites throw for real users. Worse: **once the column is dropped, you cannot roll back the code.** The old version requires the column. Your normal escape hatch is gone precisely when you'd need it.

**3. Can the irreversible part ship separately?** Yes, and it costs you almost nothing:

- **Today** — ship only the code change. Nothing reads `legacy_email` anymore; the column just sits there unused. Fully reversible; revert is a normal deploy.
- **Next week** — after the old version is out of rotation and you've confirmed zero reads, ship the `DROP` alone. One-line migration, nothing else in the diff.

**4. How fast is rollback, and who's around?** Step one reverts in minutes. A Friday afternoon deploy of a reversible change with people awake is fine — that's not the risk here. Step two has no rollback at all, so it wants a Tuesday morning and someone watching.

## About "CI is green"

Green proves the three sites you found are consistent. It doesn't prove they're the only readers. Before the drop, check outside the test's reach: raw SQL strings, ORM `SELECT *` and serializers that expose the column, CSV/data exports, analytics or BI queries, and any other service pointed at the same database. `grep -ri legacy_email` across every repo — not just this one — is what earns the drop.

★ Insight ─────────────────────────────────────
This is the "contract" step of expand/contract. Expand → backfill → dual-write → switch reads are all reversible; only contract isn't. That's the whole reason contract gets its own deploy and its own gate.
The repo-level device: a CI check that blocks `DROP`/destructive `ALTER` from landing in the same diff as application code. Then nobody has to remember this next time.
─────────────────────────────────────────────────

**Your call:** how long between the two deploys? I'd set it by "old version fully out of rotation + one full business day of traffic with the new code," not by a fixed number of days.

Want me to look at the actual diff? It's not in this repo — point me at the path or PR number and I'll check the read sites and write the CI guard.