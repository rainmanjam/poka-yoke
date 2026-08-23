No — that test wouldn't have caught this bug. The table wasn't empty; it was full of coalesced zeros. "Not empty" catches complete outages, not partial data corruption.

**What actually failed here (poka-yoke lens):**
1. **Schema coupling** — implicit contract with upstream, no validation
2. **Silent coercion** — `COALESCE(x, 0)` masked nulls as plausible values
3. **No anomaly detection** — 3 weeks of "low but okay" didn't trigger anything

**Controls that would have caught it, ranked by strength:**

| Level | Control | Catches this bug? |
|-------|---------|-------------------|
| Prevention | Schema contract test: assert expected columns exist before join | Yes — fails fast on rename |
| Prevention | Fail-loud joins: error if join key match rate drops below 95% | Yes — nulls = unmatched rows |
| Detection | Null rate assertion: revenue column null% < 1% | Yes — catches the symptom |
| Detection | Statistical bound: daily revenue within 2σ of trailing 7-day mean | Yes — "low" would be anomalous |
| Detection | Row count bounds: expect 10k–50k rows, not just >0 | Maybe — depends on drop magnitude |
| Detection | Reconciliation: compare sum to upstream source of truth | Yes — catches drift |

**Minimum viable fix:**
```sql
-- Add to your pipeline tests
SELECT 
  COUNT(*) AS rows,
  SUM(CASE WHEN revenue IS NULL THEN 1 ELSE 0 END)::FLOAT / COUNT(*) AS null_rate,
  SUM(revenue) AS total
FROM revenue_table
WHERE 
  rows BETWEEN 10000 AND 100000  -- bounds, not just >0
  AND null_rate < 0.01           -- catch the coalesce-mask pattern
  AND total > (SELECT AVG(total) * 0.5 FROM revenue_daily_history WHERE date > CURRENT_DATE - 7)
```

The schema contract is the real fix — it prevents the cause rather than detecting the symptom. Want me to sketch a contract test for your upstream dependency?