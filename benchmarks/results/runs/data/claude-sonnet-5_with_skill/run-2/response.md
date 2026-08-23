No, that test won't catch this — and it's worth being precise about why, because it's not just weak, it's aimed at the wrong hazard entirely.

**Separate what actually happened:**
- **Defect**: revenue dashboard understated for 3 weeks, caught only at finance close.
- **Mistake**: an upstream rename broke your join; the join started returning nulls for the joined column.
- **Hazard**: `COALESCE(revenue, 0)` converts "the join failed to find a match" into "revenue is zero" — a value that is completely indistinguishable from a legitimately slow day.

**Why "table isn't empty" doesn't touch this hazard:** the coalesce guarantees rows exist and guarantees the revenue column is never null. Your table was never empty during the incident — it had exactly as many rows as always, each with a plausible-looking non-null number. A row-count-floor check and a not-empty check both pass on this exact incident, unchanged. You've added a device that inspects a dimension the mistake didn't move.

Run the four data questions to see what actually would have fired:
- **Is it there?** — not the issue, table was fresh.
- **Right amount?** — not the issue, row count was fine (this is what your test checks).
- **Shaped right?** — closer: if you assert null rate on the *pre-coalesce* join result rather than the final column, this catches it. Post-coalesce, nullability tells you nothing.
- **Does it agree?** — this is the one that catches it. Reconcile summed revenue against the source system (billing/orders) daily. A join silently dropping matches still produces well-shaped, wrong data — reconciliation is the only check in the list that catches a wrong join when every individual row still looks valid.

**Proposed devices, ranked:**

1. **Control** — delete the blind `COALESCE(revenue, 0)`. A null from a join is not "zero revenue," it's "no match found," and those are different facts. Either fail the row shape check outright, or route unmatched rows to a quarantine table with the join key that didn't match. Silently defaulting is the data-pipeline equivalent of `except: pass`.
2. **Control/Warning** — assert the join match rate before publish (e.g. `% of source rows with a null joined column < threshold`, ideally 0 for a key that should always match). This is a self-check between load and publish, so it can block promotion rather than just report.
3. **Warning** — reconciliation: daily job comparing aggregate revenue in the warehouse to the source-of-truth total. Alert on drift past a tolerance you set with finance.
4. **Warning** — an ingest contract on the upstream table: producer declares column names/types, consumer validates on ingest and quarantines on mismatch instead of joining against whatever's there. This is what would have made the rename loud on day one instead of week three.
5. Keep the not-empty test — it's real, just Detection-rung for a different failure mode (total pipeline outage), not this one.

**Sweep**: grep the codebase for other `COALESCE(\w+,\s*0)` sitting downstream of a join — this is a shape, not a one-off, and it's very likely used the same way on other "safe-looking default" columns feeding other dashboards.

Want me to search this repo for other coalesce-after-join sites, or draft the join-match-rate assertion and quarantine pattern for your actual pipeline code?