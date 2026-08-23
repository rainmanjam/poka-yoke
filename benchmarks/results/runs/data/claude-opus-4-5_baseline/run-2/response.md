No — that test would have passed every day during those three weeks. Your data wasn't empty, it was *wrong*. The coalesce made sure every row had a number.

`★ Insight ─────────────────────────────────────`
This is a classic "plausible poison" failure: silent corruption that looks reasonable. Detection controls only work when the failure mode produces something detectably abnormal. Your coalesce converted "broken" into "believable."
`─────────────────────────────────────────────────`

Let me walk up the poka-yoke ladder for this failure:

**What your test catches:** total data absence  
**What actually broke:** schema drift → silent NULLs → coalesced to zero

## Controls by level

| Level | Control | What it catches |
|-------|---------|-----------------|
| Detection (weak) | `COUNT(*) > 0` | Empty table only |
| Detection (better) | Row count within ±10% of yesterday | Data volume anomalies |
| Detection (stronger) | Revenue > 0 for days with known orders | Business invariant violations |
| Prevention | `COALESCE` removal — let NULLs surface | Forces pipeline to fail visibly |
| Prevention | Schema contract test (assert column exists before join) | Catches rename at deploy time |
| Elimination | Schema registry with breaking-change detection | Upstream can't rename without coordination |

The deepest fix: **stop coalescing at the source**. If you'd written `revenue` instead of `COALESCE(revenue, 0)`, the dashboard would have shown blanks or errors — ugly, but someone notices day one, not week three.

---

What's your appetite here — quick wins (add invariant checks), or tracing back to make the pipeline fail-fast on schema drift?