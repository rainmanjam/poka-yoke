Short answer: **no.** The test you added would have passed every one of those three weeks. Here's the analysis the `retro` + `data` modes produce.

## Separate the three things

- **Defect**: revenue understated for ~3 weeks; decisions made on it; found by finance, not by the pipeline.
- **Mistake**: upstream renamed a column; your join key stopped matching.
- **Hazard** (the thing worth fixing): `COALESCE(amount, 0)` converts "this row failed to join" into "this row earned $0". The pipeline **cannot distinguish a missing value from a legitimate zero**, so a broken join produces well-shaped, plausible, wrong numbers. The table was never empty — it was full of rows that each looked fine.

Hazard catalog X2 (*silent coercion and fallback*) is exactly this: a default substituted at a boundary, with the wrongness surfacing far away.

## Why "not empty" can't catch it

Your test checks *presence* (freshness/volume floor). The failure was a *shape* and *agreement* failure: every row present, every value a number, total low. A row-count test is blind to it by construction — and per this repo's own rule, a check that wouldn't have gone red on the actual incident is a rumour, not a device.

## Devices, by rung

| Device | Rung | What it catches |
|---|---|---|
| **Remove the coalesce.** Let the join produce NULL; put `NOT NULL` on `revenue.amount` (or a `CHECK`) so the bad row cannot be written. | **Control** (if your warehouse enforces constraints; many columnar ones don't — then it's a dbt `not_null` test that *blocks promotion*, Warning) | The exact incident, at the moment it happens |
| **Join-integrity assertion**: `COUNT(*) WHERE joined_key IS NULL` ≤ a small threshold, run between staging and publish. | Warning | Any future rename, type change, or late-arriving dimension |
| **Data contract** on the upstream table: pin the columns you depend on; CI on *their* repo fails on rename, or your ingest fails loudly on schema mismatch. | Warning, at the source | The class, not just this column |
| **Reconciliation**: daily `SUM(revenue)` vs. the billing system / ledger, within tolerance. | Detection | Logic errors that keep the shape right — the only check that catches "plausible but low" |
| Volume floor against same-weekday history | Detection | Partial loads — keep it, it's just not this bug |

The structural change that makes any of these bite: **build to staging → test staging → promote on pass.** A test that runs after publication and emails someone is the same three weeks with a nicer log.

## Class sweep (do this before closing)

Grep your models for every `COALESCE(..., 0)`, `IFNULL`, `NVL`, `|| 0` on a metric column, and every LEFT JOIN whose right side feeds an aggregate. Each one is the same hazard, still armed. Report the count — "this exists at N other sites" is what justifies the constraint.

## Verify it

Rename the column in a dev schema, run the pipeline, and watch it refuse to publish. Put it back, watch it pass. Until you've seen it go red, don't write "fixed" in the retro.

## Accepted risk

If you keep a coalesce anywhere, say in a `poka-yoke:` comment *why* zero is a legitimate value there — otherwise the next engineer re-adds the fallback because NULLs "break the dashboard," and you're back here.

**Recap**: the empty-table test is a rung-3 check for a different failure. The fix is removing the silent default (Control where the engine allows), a join-null assertion that blocks publication, and a reconciliation against the ledger — then sweeping every other `COALESCE(…, 0)` in the warehouse. I didn't touch any files; if you want, point me at the model repo and I'll run the sweep and draft `docs/poka-yoke/retro-2026-08-21-revenue-coalesce.md`.