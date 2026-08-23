Using `poka-yoke:retro` for the analysis and `poka-yoke:data` for the devices — this is an incident, in a pipeline.

## No. The test you added would have passed all three weeks.

That's the important thing about it: the table was never empty. It was full of plausible, wrong numbers. A check that stays green through the exact incident it was written for is what this repo calls a rumour, not a device.

**Separating the three things** (retro step 1):

- **Defect** — revenue understated for 3 weeks; every decision made on it is now suspect, and you don't know which.
- **Mistake** — nobody's, really. An upstream team renamed a column, which they're allowed to do.
- **Hazard** — **a `LEFT JOIN` that matches nothing produces nulls, and `COALESCE(x, 0)` turns those nulls into a legal-looking value.** The pipeline had no way to fail.

The why-chain ends at a constraint, not a person: dashboard wrong → join returned nulls → column renamed upstream → *no contract made the rename loud* → and even then it should have been caught → *the coalesce erased the only signal that anything was wrong*. That coalesce is hazard **X2, silent coercion and fallback** in the catalog: it produces a plausible value from bad input, and the wrongness surfaces far away.

**Why nothing caught it:** you had no reconciliation. Of the four data questions, freshness, volume, and shape all pass here — rows arrived, on time, correctly typed, non-negative. Only *"does it agree?"* catches a wrong join, because a wrong join produces perfectly well-shaped wrong data.

## Devices, by rung

| Device | Rung | What it catches |
|---|---|---|
| Drop `COALESCE(revenue, 0)`; let revenue be `NOT NULL` at the write | **Control** | The null can't become a zero. The load fails. |
| Assert join-key match rate on staging (`orphan rows = 0`), promote only on pass | **Warning** | Any join that stops matching, from any cause |
| Daily reconciliation: warehouse revenue total vs. billing source, per day | **Detection** | Everything above, plus logic errors you didn't predict |
| Ingest contract on the upstream table — validate schema, quarantine to a dead-letter table rather than dropping | **Warning** | The rename itself, attributably |
| Your not-empty test | Detection-ish | An outage you'd have noticed anyway |

The ordering change matters more than any single check: **build to staging → assert → promote.** If assertions run after publish, bad data reaches the dashboard, which was the whole failure.

**Class sweep** — the step that's usually skipped, and where the value is. Before fixing anything, count: every other `COALESCE(…, 0)` over a joined measure, every model reading from that upstream team's tables, every `LEFT JOIN` where an unmatched row silently becomes a number. The bundled detector has X2 rules for TS/Python/Go/Rust but none for SQL, so this one is a grep over your models. *"This shape exists at 9 other sites"* is a different conversation than *"we fixed the revenue model."*

**Then prove it.** Re-point the join at the old column name against a staging copy and watch the new assertion go red, then put it back. A device that has never fired is a belief.

---

★ Insight ─────────────────────────────────────
`COALESCE(x, 0)` on a measure is the SQL twin of `except: pass` — both convert a loud failure into a quiet wrong answer. Zero is a legal revenue value, which is exactly why substituting it is undetectable downstream.
─────────────────────────────────────────────────

One thing I'd want from you before writing the reconciliation check, because it's a business call and not a technical one: **what tolerance, and what happens on breach?** Warehouse and billing rarely tie to the cent — refunds in flight, timezone cutoffs, revenue-recognition timing. Too tight and it cries wolf until people mute it; too loose and a three-week 15%-low drift slides under. Tell me the acceptable delta (absolute? percentage? per-day or trailing-7?) and whether a breach should *block the publish* or *page someone*, and I'll write the check plus the retro doc at `docs/poka-yoke/retro-2026-08-22-revenue-null-coalesce.md`.