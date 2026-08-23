Using **poka-yoke:retro** for the analysis and **poka-yoke:data** for the devices — the router sends wrong-numbers-in-a-dashboard to both.

## No. That test could not have failed here.

The table was never empty. It was full of plausible zeros. Your new test passes on the exact incident it was written for — it's a check that cannot go red in this failure mode, which is worse than no test because it reads as coverage.

**Defect**: revenue understated on the dashboard for 3 weeks; unknown number of decisions made on it.
**Mistake**: consumed an upstream column by name without a contract.
**Hazard**: `COALESCE(revenue, 0)` makes "no data" and "no revenue" the same value. The pipeline has no way to express *unknown*, so a total join failure renders as a business fact.

Why it was possible: rename → join returns null → coalesce → 0 → 0 is a legal revenue number → **nothing in the pipeline distinguishes an absent row from a zero row.** That's the missing constraint, and it's a contact-lens failure: two different things fit the same slot.

Why nothing caught it: reconciliation existed — finance's close. It ran monthly. Your detection latency *was* the three weeks.

## Devices, strongest first

| Device | Rung | Catches |
|---|---|---|
| Schema contract at ingest: assert expected columns/types, fail the load on a rename | **Control** — bad data never lands | this incident, at the source |
| Join match-rate assertion before publish (`matched / total`), staged → tested → promoted | Warning | any join that stops matching, same day |
| Delete the coalesce; let null be null and refuse to publish null revenue | Warning | the silence itself |
| Daily reconciliation: warehouse total vs billing source | Detection | wrong-but-plausible numbers generally |
| Freshness + match-rate surfaced *on the dashboard* | Detection | makes trust conditional at read time |

The first three are cheap. The match-rate check is the one that would have fired within a day, at 0%.

`★ Insight ─────────────────────────────────────`
- Coalescing to a default is the data equivalent of `except: pass` — it converts a loud failure into a quiet number.
- Renames are drops-plus-adds downstream. Additive changes are safe; renames never are.
- Assert *between* load and publish. A test that runs after publication has already lost.
`─────────────────────────────────────────────────`

## Two things before you close this

**Sweep the class.** Grep every `COALESCE(..., 0)`, `fillna(0)`, and `LEFT JOIN` on an upstream key in your models. Each one is this same incident waiting. Report the count — it changes what the fix is worth.

**Prove the device.** Rename the column in a fixture, watch the match-rate check go red, put it back. Per this repo's own rule: a check that has never once fired is a rumour.

## Your call, and it's the real design decision

The match-rate threshold is a judgment only you have: **a hard 100% (any unmatched row blocks publish) or a floor like 99.5%?** Hard-100% is Control-adjacent and will page you on legitimate late-arriving rows; a floor tolerates reality but lets a partial break through. What's your actual match rate today, and does it ever legitimately dip?

Tell me and I'll write the assertion plus the failing-first test — and I can draft `docs/poka-yoke/retro-2026-08-22-revenue-null-coalesce.md` in the skill's format if you want the incident recorded.