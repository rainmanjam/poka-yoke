No — that test would have stayed green through the entire three-week incident.

**Why it doesn't catch this:** the join returning nulls didn't shrink the table, it just filled a column with wrong values. Row count was probably identical to a healthy day. "Not empty" only answers the first, weakest form of *is it there* — it can't answer the question that actually mattered here: **does it agree** with the source system.

Walking your incident through the four checks:
- **Is it there?** Table populated, on time. Passes.
- **Right amount?** Same row count as always (it's a null-filling bug, not a row-dropping one). Passes.
- **Shaped right?** `revenue` is a valid number — 0 is a legal value. Passes.
- **Does it agree?** This is the one that would have failed, and it's the one you don't have.

Two devices, in priority order:

1. **Reconciliation on the revenue table**: sum(revenue) in the warehouse vs. the equivalent total pulled from the source system (or upstream table pre-join), daily, with a tolerance band. This is the only check that catches a wrong `JOIN` — everything else validates shape, not correctness. This directly targets what broke: the column rename nobody announced.
2. **Kill the silent COALESCE**: `COALESCE(revenue, 0)` is doing the same thing as `except: pass` — it took a loud failure (null propagating, dashboard breaking visibly) and converted it into a quiet, plausible-looking wrong number. Replace it with an assertion on null rate for the join key *before* the coalesce (e.g., `null_rate(revenue) < 1%`, alert/fail above that), or route unmatched rows to a quarantine table instead of defaulting them to zero.

If you want the durable fix instead of a patch: this is a missing data contract on the upstream column. A rename should have broken the pipeline loudly at ingest, not degraded it silently three joins downstream — that's the difference between Warning-rung and nothing at all.