Read the router, then `data` (wrong numbers in a dashboard) and `retro` (it already broke). Analysis below — no files changed.

## No. The test you added would have been green for all three weeks.

The table was never empty. It had rows, the rows had a `revenue` column, and that column held `0` because you coalesced the nulls. Row count > 0 for all 21 days. That check cannot go red in this failure mode — it's rung 3 (Detection) that detects nothing.

**The three things, separated:**

- **Defect** — revenue understated for 3 weeks; unknown number of decisions made on it; found by a human at close.
- **Mistake** — a join predicate kept referencing a column an upstream team renamed.
- **Hazard** — *the pipeline has a total function from "this data is missing" to "revenue is zero."* `COALESCE(x, 0)` over a measure is `except: pass` for numbers. Nothing in the path can distinguish "no revenue" from "no answer."

Push the whys to a constraint: nulls appeared → rename upstream → *why did a rename reach the join silently?* → the ingest reads whatever columns exist, and an absent column yields NULL rather than an error → **there is no declared schema the load is required to satisfy.** Two hazards, two devices.

## What would actually have caught it, ranked

| Device | Caught it? | Rung |
|---|---|---|
| Orphan check: `LEFT JOIN` rows where the join key is NULL must be 0 | **Day 1, definitively** | Warning, if it blocks publish |
| Schema contract at ingest — declared column manifest vs. `INFORMATION_SCHEMA`, fail on absence | **Before the join ran** | Warning |
| Reconciliation: warehouse revenue total vs. billing/ledger for the same period, daily | **Day 1**, and catches causes nobody predicted | Detection |
| Null-rate assertion on `revenue` *before* the coalesce | Day 1 | Warning |
| Row-count band vs. same-weekday history | **Probably not** — the rows were all there | Warning |
| Table-not-empty | **Never** | — |

Note row 5 honestly: volume checks don't fire here, and "plausible just low" means an anomaly band likely wouldn't either. That's exactly why the `data` skill says if you install one device, install reconciliation.

**The structural change that costs no tooling:** build to staging → assert → promote. If your checks run after publication, they're Detection by construction. Moving the assert between load and publish buys you a whole rung for free.

**Class sweep** — this is the step that gets skipped, and it's where the value is. Every `COALESCE(m, 0)` / `IFNULL` / `NVL` / `fillna(0)` over a *measure* column is the same hazard still armed. Same for every `LEFT JOIN` feeding a `SUM`, and every `SELECT *` from an upstream-owned table. I can't run that sweep from here — this session is in the poka-yoke repo, not your warehouse. Point me at the dbt project or pipeline and I'll count the sites.

★ Insight ─────────────────────────────────────
`COALESCE(x, 0)` on a measure is the highest-leverage thing to grep for in any warehouse. On a *dimension* it's usually fine; on a number that gets summed it silently converts "unknown" into an assertion of fact, and downstream `SUM` can't tell the difference. NULL propagating to a dashboard as `—` is ugly and honest; `0` is pretty and wrong.
─────────────────────────────────────────────────

## Before I write any of it — prove the instrument

Run your new test against a snapshot from the incident window. If it passes, you've confirmed it's a rumour, not a device. Do the same for each device above: break it on purpose, watch it go red.

**One decision I need from you**, because it's a business call and not a technical one: when the reconciliation breaches tolerance, does the pipeline **block publication** (dashboard shows yesterday's data plus a staleness banner) or **publish with a warning banner**? Blocking is the higher rung and means finance occasionally sees stale numbers during close; publishing-with-banner means wrong numbers stay reachable but visibly flagged. And what tolerance — exact match, or a band for timing skew between the ledger and the warehouse?

Answer those and I'll write the reconciliation model, the orphan assertion, and the ingest manifest, plus a retro doc at `docs/poka-yoke/retro-2026-08-22-revenue-nulls.md` in your repo.