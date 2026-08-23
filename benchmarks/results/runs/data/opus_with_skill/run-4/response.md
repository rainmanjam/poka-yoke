Routing: this is `retro` (the analysis) + `data` (the devices) — an incident where the failure mode was silently wrong numbers.

## No. Your test cannot fail.

Run it against the three-week-broken warehouse: the table was full, every row well-formed, `revenue = 0`. It passes. **A check that would have stayed green throughout the entire incident isn't a device — it's a rumour.** That's the disqualifying test for any check you propose here.

**Defect**: revenue understated for 21 days; decisions made on it, caught by finance at close.
**Mistake**: nobody, really — an upstream rename landed and the join stopped matching.
**Hazard**: the pipeline can lose its join key and still publish a plausible number, because `COALESCE(x, 0)` converts "this row didn't match" into "this customer earned nothing." Zero is a legal revenue value, so the wrongness is indistinguishable from a slow month.

The why-chain ends at a constraint, not a person: *why was it silent?* → nulls became zeros → *why?* → coalesce is applied at the join, where null means "missing," not "none" → **the pipeline has no way to distinguish absent data from zero data.**

**Why nothing caught it for three weeks**: the only reconciliation in your system is the finance close. Your detection latency is exactly one month by construction.

## Devices, strongest first

| Device | Rung | Catches |
|---|---|---|
| Assert unmatched-row count = 0 after the join (anti-join count, blocks publish) | Warning | this exact break, day 1 |
| Reconcile warehouse revenue total against the source/billing system, within tolerance | Detection | any wrong-but-well-shaped total — the only check that survives a logic error |
| Schema contract at ingest: assert the expected column set; a rename hard-fails the load | Control at the boundary | the whole class, before nulls exist |
| Delete the `COALESCE(..., 0)`; coalesce only where zero is the *business* meaning, never at a join | Control | hazard X2, silent coercion |
| Volume/total assertion vs. same weekday historically (floor and ceiling) | Warning | "plausible but low" |
| Build to staging → assert → promote | structural | makes all the above able to *stop* publication rather than email about it |

Keep the not-empty test; it's fine. Just don't count it.

**Class sweep — do this before fixing anything.** Every other `COALESCE(col, 0)` downstream of a join, every other join against an upstream-owned table, every dashboard whose only reconciliation is a human at close. `python3 plugins/poka-yoke/scripts/detect_hazards.py --paths <repo> --id X2` covers `.sql` as well as code. The count changes what the fix is worth.

`★ Insight ─────────────────────────────────────`
- `COALESCE` at a join is a *type* error wearing SQL clothes: it collapses `Option<Money>` into `Money` at precisely the point where `None` carries the information you need.
- Freshness and row-count checks validate *shape*. A wrong join produces perfectly well-shaped data — only reconciliation catches it. That's why it's the one to install if you install one.
`─────────────────────────────────────────────────`

**One decision is yours, and it shapes everything else**: the reconciliation tolerance. Exact match is the strongest signal but will fire on legitimate timing skew (refunds, currency, in-flight settlements); a 1% band won't catch a 0.5% mis-attribution that recurs monthly. What tolerance and comparison window does your revenue data actually justify?

Say the word and I'll write the retro to `docs/poka-yoke/retro-2026-08-22-revenue-join-nulls.md` and draft the assertions against your actual models — point me at the pipeline.