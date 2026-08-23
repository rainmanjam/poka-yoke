Using **poka-yoke:data** — this is a silent-wrongness incident, and the question is whether the new device would have caught it.

## No. Run it against the incident.

Your table was never empty during those three weeks. It had rows, on schedule, with a revenue column full of zeros. **Your new test would have been green every single day of the outage.** That's the failure mode this repo's CLAUDE.md warns about — a check that has never once gone red is a rumour, not a device. Before you keep it, break it on purpose: point it at last month's broken join and watch it pass. That's your proof it isn't the fix.

## The four questions, against your incident

| Question | Would it have caught this? |
|---|---|
| **Is it there?** (freshness) | No — data arrived on time. |
| **Is there the right amount?** (volume) | Row count, no. But **null rate on `revenue` jumping 0% → 100%** on day one, yes. |
| **Is it shaped right?** | Partly — a `sum(revenue) > 0` floor would have fired. Weak. |
| **Does it agree?** (reconciliation) | **Yes, day one.** Warehouse total vs. billing/Stripe source total. This is the one. |

## The actual defect is the `COALESCE`

`COALESCE(revenue, 0)` converts "we don't know" into "we know, it's zero" — the data equivalent of `except: pass`. Zero is a plausible business value, so it can never look wrong. Two devices, strongest first:

1. **Delete the coalesce.** Let nulls stay null and assert `null_rate = 0` on the joined key. Nulls propagate visibly; zeros hide.
2. **Quarantine, don't default.** Rows that fail the join go to a dead-letter table with a reason; alert on the rate. You keep publishing the rows you can defend and you can see exactly what you dropped.

Then: the rename itself. A contract at the ingest boundary — assert expected columns exist before the model runs — turns a rename from three silent weeks into a red build in one run, attributable to the upstream team.

## Ordering matters more than any single test

Assert **between load and publish**, not after. Build to staging → run assertions → promote on pass. If your checks run after the dashboard reads the table, bad numbers reach finance regardless of how good the checks are.

---

★ Insight ─────────────────────────────────────
Non-empty tests are popular because they're the cheapest thing that produces a green check. The generalization: a test whose passing condition is *weaker than the failure you experienced* is decorative. Always replay the incident against the new test before trusting it.
─────────────────────────────────────────────────

**One thing I'd want your input on:** the reconciliation tolerance. Warehouse vs. source rarely matches to the penny — timing cuts, refunds, currency rounding. Is a mismatch of >0.5% a hard fail that blocks publication, or a warning? Hard-fail catches this class of bug immediately but will page someone on legitimate month-end timing skew; a warning gets ignored by week three.

Tell me your stack (dbt? Airflow? plain SQL?) and your tolerance call, and I'll write the assertions.