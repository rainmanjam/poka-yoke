No, that test would not have caught this incident — and it's worth being precise about why, because the gap tells you what to add.

**Why "not empty" misses this exact failure:** the join returning nulls didn't shrink the row count — every row was still there, just with `revenue = COALESCE(x, 0)`. A row-count/non-empty check only catches missing rows. Your incident was *present rows, wrong values*, which is a different failure mode entirely and needs a different device.

**What would have caught it, in order of strength:**

1. **Kill the `COALESCE(x, 0)`.** This is the actual root cause, not the missing test. Coalescing a join-miss to 0 converts "I don't know this value" into "this value is zero" — a normal, plausible-looking number. That's the design choice that let three weeks pass. If the join can legitimately miss, that's a NULL or a quarantined row, never a fabricated 0.

2. **Null-rate assertion on the joined column**, pre-coalesce: e.g. `dbt test` asserting `null_count / row_count < 0.01` on the raw join output. A column-rename upstream would flip this from near-0% to ~100% nulls immediately — loud, same day.

3. **Reconciliation check** ("does it agree?"): sum of revenue in your table vs. a source-of-truth total (billing system, upstream table row sum). This is the one that actually catches logic/join errors, and it's the one poka-yoke-data calls out as the highest-value single device for revenue-critical tables — install this one if you install only one.

4. **Volume check with a floor**, not just non-empty: revenue trending near-zero relative to the same weekday last week should itself fire, since your dashboard did in fact go "everything looks plausible just low" — a week-over-week floor would have flagged that drop before finance did.

**Where this sits on rigor:** your current test is Detection-in-name-only — it can't even detect this class of bug. Steps 2–4 move you toward real Detection (loud failure same-day) and step 1 is the only one that's Control (the wrong number becomes structurally impossible to produce).

If you want, I can help write the null-rate + reconciliation tests against your actual dbt model — that needs to see the join/model SQL first.