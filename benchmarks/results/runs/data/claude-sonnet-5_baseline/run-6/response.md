No, not enough — and it's actually checking the wrong thing.

Your "not empty" test only catches total failure. What happened was worse: the join degraded, nulls got `COALESCE`d to 0, and the pipeline kept producing a full, plausible-looking table. Row count never dropped. That's the trap this skill calls out explicitly — a pipeline that succeeds while wrong is the dangerous case, not the one that fails loudly.

Run the four questions against this specific table:

1. **Is it there?** (freshness) — you likely have this already, not the gap.
2. **Is there the right amount?** (volume) — "not empty" is a degenerate version of this. You need a floor tied to expectation (e.g. row count within X% of the same weekday last month), not just `count > 0`.
3. **Is it shaped right?** (validity) — a null-rate check on the joined column would have caught this immediately: the day the upstream rename landed, the null rate on that column would have jumped from ~0% to ~100%.
4. **Does it agree?** (reconciliation) — this is the one that actually matches your incident. A join bug produces well-formed, non-empty, wrong data. Only a check that compares your revenue total against an independent source (upstream table sum, finance's number, a control total) would have caught "looks plausible but low."

Concretely, for this table:

- Add a **null-rate assertion** on the joined column(s) — fail if null% exceeds a small threshold, right after the join, before the `COALESCE`. The `COALESCE(x, 0)` is the thing that actively hid the bug; consider whether it should exist at all, or whether unmatched rows should instead route to a quarantine/dead-letter set you alert on.
- Add a **reconciliation check**: sum of this table's revenue vs. the upstream source table's revenue for the same window, within tolerance.
- Make both checks **block publication** (run between load and publish, staging → test → promote), not run-after-and-email. That ordering is what turns "finance flagged it in close" into "the pipeline never went green."

Also worth an upstream data contract: if that team has a habit of renaming columns without notice, validate-on-ingest against a declared schema so a rename becomes a loud quarantine event instead of a silent null-fill three joins downstream.

Want me to find the actual model/DAG file for this table and draft the specific checks (null-rate assertion + reconciliation test) against it?