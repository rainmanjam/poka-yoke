Using `retro` for the analysis and `data` for the device. Short answer: **no** — and the reason is worth separating into three things, because the test you added targets none of them.

## Defect, mistake, hazard

- **Defect**: revenue understated for three weeks; found by finance at close, not by the pipeline.
- **Mistake**: a join on a renamed column produced nulls, and `COALESCE(x, 0)` turned those nulls into plausible zeros.
- **Hazard**: the pipeline can produce a *complete, well-shaped, wrong* table. Every row is present, every column typed correctly, totals merely low. Nothing in the system distinguishes "no revenue" from "couldn't find the revenue."

The table was never empty. It had the right row count and every row had a number in it. A non-empty check would have been **green all three weeks**. That's the pattern this repo calls "a check that cannot fail" — before you trust it, break the thing on purpose: replay last month's bad column name against your new test and watch whether it goes red. It won't.

## Why until you hit a constraint

Dashboard low → join returned nulls → upstream renamed a column → *why was that silent?* → the join is a `LEFT JOIN` with `COALESCE(..., 0)` → *why does that exist?* → to avoid nulls on the dashboard → **there is no boundary where an upstream schema change is required to fail, and no point where "missing" is distinguishable from "zero."**

That last line is the hazard. `COALESCE(NULL, 0)` is `except: pass` for data.

## Devices, by rung

| Device | Rung | What it catches |
|---|---|---|
| **Data contract on ingest** — explicit column list / schema assertion on the upstream source, pipeline halts on mismatch | Warning (Control isn't available: you don't own the producer) | The rename itself, on day one, with attribution |
| **Drop the coalesce; assert null rate on the join key** — `revenue IS NULL` rate must be ~0 on the joined result, *between build and publish*, blocking promotion | Warning | Any join that stops matching, whatever the cause |
| **Reconciliation** — `SUM(revenue)` in the warehouse vs. the billing system / ledger, tolerance-bounded, daily | Detection | The only one that catches a *logic* error the data still looks healthy after |
| **Volume with a floor *and* same-weekday baseline** | Detection | Totals drifting 30% low without a single null |
| Not-empty test | Detection, and for a different defect | A pipeline that wrote nothing |

Keep your test — it's not wrong, it's just a device for a different failure. The two that would have fired on day one are the first two, and the key structural property is that they **block publication**: build to staging, assert, promote only on pass. A check that emails after the dashboard updates is the problem restated.

## Class sweep — the step that usually gets skipped

Grep every model for `COALESCE(`/`IFNULL(`/`NVL(` on a joined column, and every `LEFT JOIN` whose right side feeds a sum. Each is a place the same mistake is still available. Report the count — "six other models null-to-zero a join" changes what the fix is worth.

## Accepted risk

Without owning the producer, you can't reach Control. The contract check is the highest honest rung; say so in the retro rather than letting a passing test imply prevention.

If you share the model SQL (dbt or otherwise), I can run the sweep and draft the staging-gated assertions against the actual joins.