This is a bounded analysis — let me apply poka-yoke thinking to your mitigation.

**Short answer: No, "not empty" is insufficient.** That test would not have caught this incident — you had rows, they just contained wrong values. The real problem is deeper.

---

`★ Insight ─────────────────────────────────────`
**What failed:** Your `COALESCE(x, 0)` converted a screaming failure (NULL = "join found nothing") into silent plausibility. The system's natural error signal got muted.

**Control hierarchy (strongest to weakest):**
- **Elimination** — make the error impossible
- **Prevention** — stop before error occurs  
- **Detection at source** — catch when it happens
- **Detection downstream** — catch later
- **Mitigation** — reduce damage after the fact

Your "not empty" test is weak detection-downstream. Here's what each level would look like for this failure:
`─────────────────────────────────────────────────`

| Level | Control | What it catches |
|-------|---------|-----------------|
| **Elimination** | Schema contract tests in CI — fail the upstream deploy if breaking changes land without coordination | This exact incident |
| **Prevention** | Replace `COALESCE(revenue, 0)` with explicit NULL handling that alerts or fails | NULLs surfacing at all |
| **Detection at source** | Row count / sum assertions at transform time with tolerance bands (±20% of 7-day average) | Anomalous data immediately |
| **Detection downstream** | Your "not empty" test | Total absence only |

---

**Recommended controls (pick 2-3):**

1. **Kill the COALESCE-to-0 pattern** — If a join returns NULL, that's data saying "something broke." Coalescing masks it. Either fail loudly or log an alert.

2. **Add tolerance-band assertions** — "Revenue today vs 7-day rolling average should be within ±30%." Catches "plausible but wrong" that "not empty" misses.

3. **Schema contract tests** — Register expected column names/types. Fail CI when upstream changes break contracts before they reach prod.

4. **Freshness + completeness checks** — Not just "rows exist" but "expected row count within range" and "max timestamp within N hours."

---

Would you like me to sketch out specific dbt/SQL test patterns for any of these, or help design the tolerance-band assertion logic?