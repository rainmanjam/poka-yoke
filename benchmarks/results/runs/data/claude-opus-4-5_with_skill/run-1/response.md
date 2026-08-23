No, a "table isn't empty" check wouldn't have caught this incident. Let me walk through why, using the poka-yoke framework.

---

`★ Insight ─────────────────────────────────────`
Your incident is the canonical data failure mode: **silence is the defect**. The pipeline succeeded. The numbers looked plausible. The COALESCE to zero actively hid the problem by producing "revenue just low" instead of "revenue is null everywhere." Three weeks of decisions were made with wrong data.
`─────────────────────────────────────────────────`

## Why "not empty" fails

| What broke | Would "not empty" catch it? |
|------------|----------------------------|
| Upstream renamed column | No — rows still exist, revenue = 0 |
| Join returned nulls | No — nulls coalesced to 0, table still populated |
| Revenue showed "low but plausible" | No — zero is a valid number |

Your check reaches **Detection rung**, but it's calibrated for *total* failure. This incident was *partial* — you had rows, they just had zeros where they should have had dollars.

## Devices that would have caught it

**1. Data contract on the source (Control)**
The upstream team renames a column — the contract breaks *immediately*, before any bad data enters your pipeline. This is the highest rung available for schema drift.

```yaml
# Example: Great Expectations or dbt contract
columns:
  - name: revenue_amount  # exact name, not "whatever's there"
    type: numeric
    not_null: true
```

**2. Reconciliation to source (Detection, but the right shape)**
Daily: does `SUM(revenue)` in your table match `SUM(revenue)` in the source system? This catches logic errors, not just shape errors — including wrong joins.

```sql
-- The one device to install on revenue-critical tables
SELECT ABS(warehouse.total - source.total) / source.total AS drift_pct
FROM (SELECT SUM(amount) as total FROM warehouse.revenue) warehouse,
     (SELECT SUM(amount) as total FROM source.billing) source
WHERE drift_pct > 0.01  -- 1% tolerance
```

**3. Volume vs. historical baseline (Detection)**
"Is today's revenue within 2 standard deviations of the same weekday last 4 weeks?" This catches "plausibly low" because the baseline knows what normal looks like.

**4. Null rate monitoring on join columns (Warning)**
Alert when null rate on `revenue_amount` exceeds historical norm. Catches the symptom even if the COALESCE masks it downstream.

## The COALESCE problem

This line is the hazard:
```sql
COALESCE(revenue_amount, 0)
```

It converts "I don't know" into "zero" — and in revenue context, those are catastrophically different. Consider:
- Remove the COALESCE and let nulls propagate (pipeline fails loudly)
- Or quarantine: route rows with null revenue to a dead-letter table, alert on rate

## What to install

| Device | Rung | Catches this incident? | Catches other failures? |
|--------|------|----------------------|------------------------|
| Contract on source schema | Control | **Yes** — breaks on rename | Schema drift of any kind |
| Reconciliation to source | Detection | **Yes** — totals diverge | Logic errors, bad joins |
| Volume vs. same weekday | Detection | **Yes** — "low" becomes "anomalously low" | Partial loads, filter bugs |
| Null rate alert | Warning | **Yes** — spike on join failures | Upstream nullability changes |
| Table not empty | Detection | No | Only total absence |

**Recommendation**: Install reconciliation first — it's the one device that catches *wrong numbers*, not just *wrong shape*. Then add a data contract so upstream can't rename columns without your pipeline objecting.

Would you like help writing the reconciliation check or the contract spec?