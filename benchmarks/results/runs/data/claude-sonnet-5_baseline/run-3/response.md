No — a "table isn't empty" test only checks volume, and this incident wasn't a volume failure. The table stayed full the entire three weeks; every expected row was still there. What broke was **shape** and **agreement**: the join started missing keys, and `COALESCE(revenue, 0)` converted those misses into valid-looking zeros. A non-empty check can never see that, because the row count didn't change — only the values inside rows did.

Here's why each of the four data-hazard lenses matters for this specific incident:

| Lens | Would it have caught this? | Why |
|---|---|---|
| **Is it there?** (freshness) | No | Data kept arriving on schedule |
| **Is there the right amount?** (volume — your test) | No | Row count was unchanged; nulls, not missing rows |
| **Is it shaped right?** (schema/validity) | **Partially** | A null-rate assertion on the joined revenue column would have fired — nulls spiked from ~0% to matching the renamed column's share |
| **Does it agree?** (reconciliation) | **Yes** | Comparing warehouse revenue total to the source system total would have shown a gap the day the column was renamed |

The root cause is `COALESCE(revenue, 0)` — that's what turned a loud failure (nulls propagating, join breaking visibly) into a silent one (plausible-looking low numbers). That line is the actual hazard, independent of what test exists.

What closes this class of failure, strongest device first:

1. **Delete the coalesce.** Let nulls be nulls, or better, let the join failure throw. Right now you have code actively converting a signal into noise.
2. **Assert join-key match rate ≈ 100%** between the two tables, checked in the pipeline before publish, not after. This is what would have gone red on day one of the rename.
3. **Reconciliation check**: warehouse revenue sum vs. source-system revenue sum, daily, with a tight tolerance. This is the one device that would catch *any* future logic error in this join, not just this specific column-rename scenario.
4. **A data contract on the upstream table** — if they can rename columns without your pipeline erroring, the same incident happens again next quarter with a different column.

Your empty-table test isn't wrong to have, it's just answering a question ("did the pipeline run at all") that wasn't the one this incident asked. Want me to help write the null-rate/reconciliation assertions into the actual pipeline code, or do you need to settle the tolerance thresholds with finance first?