Using **poka-yoke:data** (wrong numbers in a warehouse/dashboard), with the **retro** three-part split since this already broke.

## Short answer: no, and the specific reason matters

**Your test would have been green for all three weeks.** The revenue table was never empty — it was full, and every row looked fine. You've added a check that cannot fail on the incident it was written for. In this repo's terms that's the recurring failure mode: not broken code, but *an instrument that can't go red*.

Keep it — it catches a total load failure, which is a real thing. Just don't count it as the fix.

## Separate the three things

- **Defect** — revenue understated for three weeks; every decision made on it is now suspect.
- **Mistake** — an upstream team renamed a column. That's not a mistake anyone can stop; renames are normal.
- **Hazard** — two of them, and the second is the expensive one:
  1. A join that matches **zero rows succeeds.** Nothing asserts that a join produced the cardinality you expected.
  2. `COALESCE(revenue, 0)` sits at the aggregation boundary. Null means *"we don't know."* Zero means *"we know, and it's nothing."* Coalescing destroys that distinction **irreversibly** — after that line runs, no downstream check anywhere can recover the difference. It is `except: pass` written in SQL.

The whys end at a constraint, not a person: *dashboard low → join returned nulls → column renamed → nothing validated the input schema → **the pipeline reads upstream columns by assumption, and there is no contract that makes a rename a failure.***

**Why nothing caught it:** the reconciliation *did* exist — it's called financial close. It ran monthly, with three weeks of lag, executed by a human. That's rung 3 at its slowest.

`★ Insight ─────────────────────────────────────`
- Of the four data questions (fresh / right amount / right shape / does it agree), **only "does it agree" catches this class.** Freshness, row counts, and null rates all pass here — the table was fresh, full, and had no nulls, *because you coalesced them away*.
- Coalescing to zero is uniquely bad for money because 0 is a plausible value. `COALESCE(x, -1)` would have screamed on day one. The default value's plausibility is the whole hazard.
`─────────────────────────────────────────────────`

## The devices, strongest first

| # | Device | Rung | Catches |
|---|---|---|---|
| 1 | **Schema contract at ingest** — explicit column list, assert the expected set on read, quarantine unknown rows to a dead-letter table rather than dropping | Warning (closest to Control you can buy) | *Exactly this incident.* Rename → hard failure at the boundary, attributable to upstream |
| 2 | **Reconciliation to source, blocking publish** — daily warehouse revenue total vs. the billing system total, within tolerance | Warning | Any wrong join producing well-shaped data. This is the one to install if you install one |
| 3 | **Join match-rate assertion** — after the join, assert unmatched-row fraction < threshold | Warning | Renames, key drift, silent fan-out |
| 4 | **Ban null→0 on money at aggregation** — let null propagate, or bucket it as explicitly "unknown" and render it | Warning | Turns the *next* silent wrongness back into a loud one |
| 5 | **Build → staging → test → promote** ordering, so 1–4 can actually stop publication instead of emailing about it | structural | Everything above. Costs no new tooling |
| 6 | **Freshness + last-updated + row-count surfaced on the dashboard face** | Detection | Stale tables, which look perfectly healthy |
| 7 | **The regression test you actually want**: fixture with the column renamed → assert the pipeline *fails* | Detection | Proves 1–3 are real |

Honest rung accounting: none of these are Control. Control would mean the warehouse physically refusing the write, and most columnar engines won't give you that. A dbt test is Detection dressed as prevention unless it gates promotion — which is why #5 is doing more work than it looks like.

## Two things before you build any of it

**Prove each check fails.** Rename the column in a fixture, run the pipeline, watch it go red, put it back. A check that has never once gone red is a rumour.

**Sweep the class.** The question isn't "is the revenue join fixed" — it's *how many other models coalesce a money or count column to zero, and how many other joins have no match-rate assertion?* One grep for `COALESCE(.*, 0)` across your models will probably reframe how much this work is worth.

## Two decisions I can't make for you

These shape the implementation and they're genuinely yours:

1. **Reconciliation tolerance and breach behaviour.** Revenue rarely ties to the penny (timing, refunds, FX). Is the band 0.1% or 1%, and on breach does the pipeline *block publication* (finance sees stale-but-correct) or *publish with a banner* (finance sees fresh-but-flagged)? Blocking is the stronger device; it also means a flaky upstream can dark the dashboard during close.
2. **What a null revenue row should become.** Excluded from the total, or surfaced as an explicit "unrecognised: $X" line? The second is more honest and more annoying — and the annoyance is the point, since it's what makes the next break loud.

Point me at the DAG or the dbt models and I'll write the contract, the reconciliation assertion, the match-rate check, and the rename-fixture regression test — plus a `docs/poka-yoke/retro-2026-08-22-revenue-nulls.md` with the class-sweep results. I'll show you the diff before touching anything.