No — that test would have stayed green for the entire three weeks. Applying the retro + data mode to this:

**Separate the three things**
- **Defect**: revenue dashboard understated for 3 weeks, caught only at finance close.
- **Mistake**: the join's null results were coalesced to 0 instead of being surfaced.
- **Hazard**: *the pipeline has no way to distinguish "true zero" from "the join failed."* `COALESCE(..., 0)` erases that distinction at the exact point where it mattered most.

**Why "not empty" doesn't reach the hazard**: row count is the *volume* check, and this defect didn't touch row count — every row was still there, just with a wrong value in one column. You need the *reconciliation* check (does the warehouse total match the source system?) — that's the only one of the four data questions that catches a join that's silently wrong but still well-shaped. An empty-table check and a wrong-total check are different failure modes; you built a device for a failure mode that didn't happen.

**Why it was possible, one level further**: the join key came from an upstream column with no contract — nobody had to announce the rename, so the pipeline had no way to fail loudly on it. That's the actual missing constraint, not "we didn't have enough tests."

**Devices, by rung, strongest first:**

| Device | Rung | What it catches |
|---|---|---|
| Reconciliation check: warehouse revenue sum vs. source-system total, blocking promotion to the published table | Warning (blocks pipeline before publish) | The exact defect that happened |
| Null-rate assertion on the joined column *before* the coalesce — fail if nulls exceed a threshold (ideally near-zero) | Warning | Any future join breakage on this key, regardless of cause |
| Replace `COALESCE(x, 0)` with `COALESCE(x, 0)` only after the null-rate assertion passes, or don't coalesce at all — let nulls surface as nulls/errors downstream | Control-ish | Removes the specific mechanism that made this silent |
| Data contract with the upstream team on that column (schema + rename = breaking change, versioned) | Control at the boundary | The root cause: renames landing without warning |
| Row-count / not-empty test (what you have) | Detection, and only for a different failure mode | Total pipeline failure, not silent drift |

**Class sweep** — this is the step worth doing before you call it closed: grep for every other `COALESCE(..., 0)` (or equivalent default-fill) sitting downstream of a join anywhere revenue, cost, or other finance-adjacent numbers are computed. Each one is the same hazard waiting to fire quietly. Any join with a fallback default is a candidate.

So: keep the not-empty test (it's cheap and catches a real, different scenario), but it's Detection for the wrong defect. The device that actually closes this hole is the reconciliation check against source-system totals, gated before publish, plus killing or gating the coalesce-to-0 so a join failure can't disguise itself as a legitimate zero.

Want me to help write the reconciliation query and null-rate assertion against your actual pipeline code?