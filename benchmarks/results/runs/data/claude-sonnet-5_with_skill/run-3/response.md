No — a not-empty check tests for the wrong failure mode. Walk through what actually happened: the rename didn't drop rows, it broke the join key. Your ETL still ran, still inserted one row per expected entity, and `COALESCE(revenue, 0)` papered over the nulls. The table was full-looking, correctly-shaped, non-null, and wrong for three weeks straight. A row-count assertion would have stayed green the entire time, because row count was never the thing that broke.

**★ Insight ─────────────────────────────────────**
This is the distinction poka-yoke's data mode draws between four questions you can ask of any table: *is it there* (freshness), *is there the right amount* (volume), *is it shaped right* (schema/nullability), and *does it agree* (reconciliation against source). Your test answers "is there the right amount" — but the bug lived in the fourth question, the only one that catches a join that's silently wrong rather than silently empty. Everything upstream of reconciliation can pass while the total is off, because a bad `JOIN` produces *well-shaped* wrong data, not malformed data.
**─────────────────────────────────────────────────**

What would actually have caught this, strongest device first:

1. **Delete the `COALESCE(revenue, 0)`.** This is the actual root cause — it's converting a loud failure (nulls propagating, something breaking downstream) into a quiet, plausible-looking one. If a null shouldn't happen, let it be null and fail the pipeline on it, don't launder it into a number.
2. **Assert the join-key match rate before the coalesce runs.** Something like "unmatched rows / total rows < 0.1%", checked between load and publish so it can block promotion — not a test that runs after the dashboard is already showing the bad number.
3. **Reconcile revenue against the source system total daily.** This is the one that would have caught it even if you never touch the coalesce — sum-of-warehouse vs. sum-of-source diverging is unambiguous, unlike a plausible-but-low number a human has to notice.
4. **A data contract on the upstream column**, if you control or can negotiate with that team — so a rename is a breaking-change event they announce, not a silent behavior change you absorb.

Rung-wise: your current test is Detection at best (row count, not correctness) and didn't even fire here. #1 is closest to Control — it doesn't prevent the upstream rename, but it prevents your pipeline from *hiding* the consequence. #2–3 are Detection, but detection that can actually block publication, which is the load-bearing distinction from a test that emails someone after the dashboard's already wrong.

Want me to write the join-key match-rate assertion and the reconciliation query against your actual schema? I'd need the join and the source-of-truth table to write something concrete rather than a template.