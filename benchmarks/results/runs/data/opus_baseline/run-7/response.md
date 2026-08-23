No — and it's worth being precise about why, because the test you added is the kind that can't fail.

During those three weeks the revenue table was full. Rows were present, the join matched nothing, `COALESCE` turned every null into 0, and the table stayed non-empty the entire time. Your new test would have been green throughout the incident. It's a check that has never gone red and structurally cannot go red for the failure you actually had.

`★ Insight ─────────────────────────────────────`
The defect wasn't the rename — upstream teams rename columns. The defect was that a *join failure* and a *real zero* were indistinguishable by the time the number reached the dashboard. `COALESCE(x, 0)` is the data equivalent of `except: pass`: it converts a loud failure into a plausible number.
`─────────────────────────────────────────────────`

What would have caught it, ordered by how early it fires:

1. **Kill the coalesce, or split it.** A null on an *unmatched* row and a null on a *matched* row with no revenue are different facts. Coalesce the second, fail on the first. This alone turns the incident into a red pipeline on day one.
2. **Join-integrity assertion.** After the join, assert match rate — `unmatched_keys = 0`, or `match_rate >= 0.999`. A join that silently stops matching is the single most common way a warehouse produces well-shaped wrong numbers.
3. **Schema contract on the upstream input.** Assert the expected columns and types exist before you read them. A rename then fails *attributably*, at the boundary, naming the producer — instead of surfacing as your dashboard being wrong.
4. **Reconciliation to source.** Daily: warehouse revenue total vs. the billing/ledger system, within tolerance. This is the only check that catches logic errors you haven't imagined, and revenue is exactly the table that earns it.
5. **Variance band on the metric.** Revenue vs. same weekday, trailing 4 weeks. "Plausible but low" is precisely what a band catches and a human eyeballing a chart doesn't.

And the structural piece that matters more than any individual check: **these have to run between load and publish, and block promotion.** Build to staging → assert staging → swap. Checks that run after publication and email a failure still let finance see the wrong number first.

Two things to do beyond the fix:

- **Prove each check fails.** Re-point the join at the old column name, watch it go red, put it back. A check you haven't seen fail is a rumour.
- **Sweep for the same hazard elsewhere.** Grep for `COALESCE(..., 0)` and `IFNULL(..., 0)` on any column that comes from a join. This pattern is rarely used once.

Two numbers here are genuinely yours, not mine: the **reconciliation tolerance** (exact match? within $0.01? within 0.1% for timing skew?) and the **match-rate floor** (is 99.9% healthy for your data, or should it be 100%?). Tell me those and point me at the model, and I'll write the assertions and the deliberately-failing test for each.