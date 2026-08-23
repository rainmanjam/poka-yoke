Read the router, then `data` (the domain match for wrong numbers) and `retro` (something already broke), plus the hazard catalog. Both apply here — retro for the analysis, data for the devices.

## No. That test would have been green for all 21 days.

The table was never empty. It was full of plausible zeros. A check that stays green through the entire incident it was written for isn't a device, it's a rumour — and this repo's own rule is that you prove a check fails before you trust it. Replay a snapshot from week two against your new test and watch it pass. That's the demonstration, and it takes ten minutes.

**Separating the three things** (they get conflated, which is why these repeat):

- **Defect** — dashboard understated revenue for three weeks; unknown number of decisions made on it.
- **Mistake** — upstream renamed a column; nobody downstream was told.
- **Hazard** — `COALESCE(revenue, 0)` makes *"no matching row"* and *"genuinely zero revenue"* the same value. That's the system property, and it's the one worth fixing.

The why-chain ends at a constraint, not a person: join returned nulls → nulls became 0 → *why was that legal?* → the coalesce was written to keep the dashboard from showing blanks → **there is nothing in the pipeline that distinguishes missing data from zero data, and nothing that compares the total to a source of truth**. Finance's close *was* your reconciliation job. It runs monthly.

## Devices, strongest first

| Device | Rung | Catches |
|---|---|---|
| Stop coalescing absence to zero — null out, or carry a separate `matched` flag | **Control** | the entire class; the wrong value loses its spelling |
| Assert join match rate against a floor **between load and publish**, promote only on pass | **Warning** | any future join breakage, before the dashboard sees it |
| Contract check on upstream schema at ingest; quarantine to a dead-letter table, don't drop | **Warning** | renames and type narrowing, attributably |
| Daily reconciliation: warehouse total vs. source-of-truth total | **Detection** | wrong joins that produce perfectly well-shaped data |
| Surface `last_updated` on the dashboard itself | **Detection** | staleness, which looks completely healthy |

If you install one, install reconciliation — it's the only check on that list that catches a logic error the data still looks fine after. Everything above it validates shape, and your data's shape was never wrong.

The ordering matters as much as the checks: build to staging, test staging, promote on pass. A suite that runs *after* publication and emails a failure still lets bad numbers reach finance.

★ Insight ─────────────────────────────────────
`COALESCE(x, 0)` is the SQL spelling of `value || default` — hazard X2, silent coercion. It's not a data-modeling choice, it's an error handler that returns a plausible number instead of failing. The tell is that it was added for cosmetic reasons (blank cells look broken) and silently took on semantic load.
─────────────────────────────────────────────────

**The sweep is where the real value is.** Grep every model for `COALESCE(..., 0)`, `IFNULL`, `NVL`, and `.fillna(0)` on any measure column. Each one is this same incident waiting on a different upstream team. Report the count — "this hazard is live at 11 other places" changes what the fix is worth.

## The decision I can't make for you

Reconciliation needs a breach threshold, and that's a business call, not an engineering one. Warehouse-vs-source totals never match exactly — late-arriving rows, timezone cutoffs, refunds posted after close. Too tight and the alert gets muted within a week, which is worse than not having it. Too loose and it misses a repeat of this.

What's the smallest revenue delta that would actually change a decision at your company — a fixed dollar floor, a percentage, or "N consecutive days outside tolerance"? Give me that and I'll write the check and its marker comment.

Want me to draft the retro write-up as a file? It'd go in your pipeline repo, not this one, so tell me the path.