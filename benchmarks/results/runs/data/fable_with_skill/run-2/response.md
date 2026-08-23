Short answer: **no — and the test you added would have passed every day of those three weeks.** The table was never empty; it was full of plausible-looking zeros. A check that wouldn't have gone red during the actual incident is, in this repo's words, a rumour, not a device.

Here's the analysis the way the `retro` + `data` modes frame it.

## Separate the three things

- **Defect:** revenue dashboard under-reported for ~3 weeks; finance caught it at close.
- **Mistake:** upstream renamed a join column; the join stopped matching.
- **Hazard:** `COALESCE(x, 0)` converts "I don't know this value" into "this value is zero" — a *silent* failure — and nothing between the join and the dashboard asserts that the join actually matched anything.

Your test addresses none of these. It checks for a failure mode (empty table) that didn't occur.

## Why it was possible (the why-chain)

Wrong revenue → join returned nulls → nulls became 0 → **why?** because `COALESCE` was there → why was that safe-looking? because nobody distinguished "legitimately no revenue" from "join failed" → **the pipeline has no way to tell the difference, and nothing measures match rate.** That last line is the hazard: a missing constraint, not a missing person.

## Why nothing caught it

Every assertion you had was about *shape*. The data was perfectly well-shaped and wrong. The skill is blunt about this: only **reconciliation** catches a logic error the data still looks healthy after.

## Devices, strongest first

| Device | Rung | What it catches |
|---|---|---|
| **Reconciliation to source of truth** — daily total vs. billing/ledger, tolerance ±X%, *blocks publication* on mismatch | Warning | Exactly this incident, on day 1 |
| **Join match-rate assertion** — `count(matched)/count(left) >= 0.99`, fails the build | Warning | Any future column rename / key drift, on day 1 |
| **Data contract on the upstream table** — schema pinned, ingest fails on a renamed column | Warning (Control if the producer's CI enforces it) | The cause, not the symptom |
| **Remove the `COALESCE` for unmatched rows**; let the null propagate to a `NOT NULL` / `CHECK` constraint, or route unmatched rows to a quarantine table | Control where the engine enforces it | Makes "unknown" unable to impersonate "zero" |
| **Volume against same-weekday history** (floor and ceiling) | Detection | Partial loads, fan-out |
| Your non-empty test | Detection | Only a total load failure |

Structural point from the `data` skill: these must run **between build and publish** — stage, test, promote on pass. A test that emails after the dashboard refreshes still lets finance find it first.

## Class sweep (the step that gets skipped)

Before closing this: grep every `COALESCE(..., 0)` / `IFNULL` / `fillna(0)` sitting downstream of a `LEFT JOIN` in your models. Each one is the same hazard, still armed. Report the count — "the same pattern exists in N other models" changes how much the fix is worth.

## Honest rung accounting

Most of what you can actually install here is Warning, not Control — a dbt-style test runs after the row exists. The only true Control is the contract enforced on the producer's side (they can't merge the rename) or a constraint the warehouse enforces at write. Push for the contract; it's the one that stops the upstream team from doing this to you again.

If you want, I can draft the retro to `docs/poka-yoke/retro-2026-08-21-revenue-coalesce.md` and sketch the reconciliation + match-rate assertions against your actual models — point me at the repo.