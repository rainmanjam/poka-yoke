No — and the reason is precise: **the table was never empty during the incident.** The rows were all there; a column in them was wrong. Your new test would have been green for the entire three weeks. It guards against a failure you didn't have and not against the one you did.

Run the outage through the four data questions:

| Question | Would it have fired? |
|---|---|
| Is it there? (freshness) | No — loads ran on schedule |
| Is there the right amount? (row count, your test) | No — same row count |
| Is it shaped right? (null/value checks) | **Yes** — if the null rate on the joined column was asserted *before* the coalesce |
| Does it agree? (reconciliation) | **Yes** — warehouse revenue vs. source-system total would have diverged on day one |

So the devices that actually close this class of bug, strongest first:

1. **Reconciliation on the revenue table.** Sum of revenue in the warehouse must match the billing/source system within a tolerance, and the check must be able to *block publication* (build to staging → test → promote). This is the only check that catches logic errors, and it's the one that catches the *next* variant of this bug too — the one that isn't a rename.

2. **Kill the coalesce, or make it count.** `COALESCE(x, 0)` on a money column is `except: pass` for data: it converts a loud null into a plausible zero. Either let the null propagate and assert `not_null` on the joined column, or keep the coalesce but assert the *rate* of rows hitting the fallback is ~0. A join that matches nothing should fail the run, not produce a round number.

3. **Schema contract on the upstream boundary.** Assert the exact columns you depend on exist, on ingest, so a rename fails at the source with a message naming the column — not three hops downstream as nulls. Treat a rename as drop-plus-add because that's what you experienced.

4. **Dashboard shows last-reconciled, not just last-loaded.** Finance shouldn't have been the detector.

Keep the non-empty test — it's cheap and catches a different failure. Just be clear with yourself that it's not the regression test for this incident. And per this repo's own rule: once you've written the null-rate or reconciliation check, **break the join on purpose and watch it go red** before you trust it. A check that has only ever passed is a rumour.

One honest caveat on rung: most of these are Detection, not Control. A true Control would be `NOT NULL` on the joined column at write time — worth adding if your warehouse enforces it; many columnar ones don't.

If you want, point me at the model/SQL for the revenue table and I'll sweep for every other coalesce-to-zero and inner-join-that-should-be-left that's still sitting there with the same hazard.