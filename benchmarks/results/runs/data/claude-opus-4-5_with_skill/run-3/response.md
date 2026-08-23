Excellent, I now have the full picture. Let me apply the poka-yoke-retro framework to your incident.

---

## Retro Analysis

**Defect**: Revenue dashboard understated revenue for 3 weeks; discovered by finance during close.

**Mistake**: Pipeline join returned nulls after upstream renamed a column.

**Hazard**: `COALESCE(revenue, 0)` converted join failures into plausible-looking zeros — the pipeline couldn't distinguish "no data" from "zero revenue."

---

## Is your test enough?

**No.** Your "table isn't empty" test is **Rung 3 (Detection)**, and it only catches the extreme case — a completely empty table. Your actual incident produced a table that was *full of zeros*, which would pass this test.

`★ Insight ─────────────────────────────────────`
The core hazard here isn't missing data — it's *silent degradation*. `COALESCE(..., 0)` is the data equivalent of `except: pass`. It masks failures as plausible-looking results. Three weeks of wrong numbers that "look low" is worse than three weeks of a failing pipeline.
`─────────────────────────────────────────────────`

---

## What would have caught this

| Device | Rung | What it catches |
|--------|------|-----------------|
| **Table not empty** (you have this) | Detection | Total pipeline death |
| **Row count floor** (e.g., ≥80% of same-weekday last week) | Warning | Partial loads, filter failures, join misses |
| **Reconciliation to source** (your revenue sum matches Stripe/source) | Warning | Logic errors, wrong joins, silently dropped rows |
| **Schema contract with upstream** (column rename = breaking change, not silent null) | Control | The actual incident — join breaks loudly |
| **Remove COALESCE on critical columns** (let nulls propagate to dashboards) | Control | Forces investigation instead of hiding problems |

---

## Recommendations, in priority order

1. **Add volume comparison**: Assert that today's revenue row count and sum are within a reasonable band of the same weekday N weeks ago. This catches "plausible but low" — exactly what you experienced.

2. **Reconcile against the source**: If you have an authoritative revenue number (Stripe, your transactional DB), assert your warehouse total matches within tolerance. This is the only check that catches wrong joins.

3. **Schema contract with upstream**: Require the upstream team to declare their schema. Column renames become breaking changes that fail loudly, not silent nulls.

4. **Stop using COALESCE on revenue paths**: Let nulls propagate. A dashboard showing NULL is ugly but honest; a dashboard showing $0 is a lie that looks like data. If your BI tool can't handle nulls, coalesce *at the dashboard layer* with a warning badge, not in the pipeline.

---

## The class sweep question

Is `COALESCE(..., 0)` used elsewhere in revenue-critical paths? That pattern is the actual hazard — every instance is another place you can have three weeks of plausible-looking wrong numbers.

Would you like me to scan your pipeline code for that pattern and for joins that could silently return nulls on schema changes?