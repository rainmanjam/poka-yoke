No — and it's worth being precise about *why*, because the test you added is the specific failure mode this repo is built around: **a check that could not have caught the incident it was written for.**

During all three weeks, the revenue table had rows. Plenty of them. Your not-empty test would have been green the entire time. It's not a weak device, it's a zero device — it has never had a chance to go red and it wouldn't have.

★ Insight ─────────────────────────────────────
The `COALESCE(x, 0)` is doing double duty here: it's a null-handling convenience *and* an unintentional error suppressor. It converted "this join found nothing" into "this customer earned nothing" — two facts that are indistinguishable downstream. That's the data equivalent of `except: pass`.
─────────────────────────────────────────────────

**What would have caught it, strongest first:**

1. **Reconciliation to source.** Warehouse revenue total vs. the billing system's total for the same window, asserted to a tolerance. This is the only check on the list that catches a *logic* error — a broken join produces perfectly well-shaped, wrong data. Finance did this manually at close. Do it nightly, in code. If you install one thing, this.
2. **Null-rate assertion on the join key, *before* the coalesce.** The coalesce is fine as an output convention; the sin is that nothing measured how often it fired. Assert `null_rate < baseline` on the pre-coalesce column and the rename becomes loud on day one.
3. **A schema contract on the upstream table.** A rename is a drop plus an add, and a drop should fail your ingest, not silently produce nulls.
4. **Volume/magnitude bounds on the metric itself** — revenue vs. same-weekday-last-week, not vs. yesterday. "Plausible but low" is exactly what a ±X% band catches.
5. **Assert between load and publish.** Build to staging → test staging → promote on pass. If your tests run after publication, bad numbers still reach the dashboard; you just find out faster. This costs no new tooling and is usually the highest-leverage structural change.

**Two decisions that are genuinely yours, not mine:**

- **Reconciliation tolerance.** Too tight and it fires on timing skew between systems; too loose and it misses a 4% shortfall. What's the smallest revenue error finance would actually care about?
- **Failure behavior.** On a failed reconciliation, does the dashboard show stale data with a visible "last verified" stamp, or show nothing? Stale-but-labeled is usually right for revenue — but it depends whether your consumers read timestamps.

Tell me the stack (dbt? Airflow? which warehouse?) and I'll write the actual assertions plus the negative test that proves each one goes red when you break the join on purpose. That last part is the non-negotiable half — a check you haven't watched fail is a rumour, not a device.