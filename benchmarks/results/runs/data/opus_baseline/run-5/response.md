Using **poka-yoke:data** — this is the canonical silent-wrongness incident.

**No. And worse: your new test would have passed for all three weeks.**

The table was never empty. It was full of plausible zeros. A check that stays green through the exact incident it was written for isn't a device, it's a rumour — same failure mode this repo's CLAUDE.md warns about (`a check that cannot fail`).

**The actual fault-masker is the `COALESCE`.** The join *did* fail loudly — it produced nulls, which is a pipeline screaming. You caught the scream and turned it into `0`. That's `except: pass` in SQL. Nothing downstream can distinguish "no revenue" from "no join." Every other device below is second-best to just deleting that `COALESCE` and letting nulls propagate to a `NOT NULL` assertion.

Ranked by what would have caught *this*:

1. **Join match-rate assertion.** `count(*) where dim_key is null / count(*)` on the fact table. Expected ~0%; it went to 100% on day one. This is the sharpest generalization of your incident — a rename, a bad key type, a filtered dimension all trip it.
2. **Reconciliation to source.** Warehouse revenue total vs. the source system total, within tolerance. It's the only check in the catalogue that catches *logic* errors — a wrong join produces perfectly well-shaped, wrong data. Finance found the bug this way, three weeks late and by hand. Make that a job.
3. **Schema contract at the boundary.** Assert the columns you depend on exist with expected types, before the transform runs. A rename should be a hard break, not a nullable left join. Treat rename = drop + add, because that's what you experienced.
4. **Volume vs. same weekday last week**, not `> 0`. Floor *and* ceiling. (Day-over-day cries wolf every Monday.)
5. **Assert between load and publish.** Build to staging → test staging → promote on pass. Right now your tests, whatever they check, run beside the pipeline rather than in front of the dashboard. This is the structural change that costs no new tooling.

Be honest about rungs: 1–4 are **Detection** (bad data exists, you find out fast). Only a `NOT NULL` constraint at the write is **Control**. Don't let anyone log this as "fixed" on the strength of a dbt test.

**Then prove each one fails.** Check out the pre-rename schema in a fixture, rename the column, watch each check go red, put it back.

★ Insight ─────────────────────────────────────
Nulls are information. `COALESCE(x, 0)` on a *measure* destroys the distinction between "measured zero" and "unmeasured" — the two things a dashboard most needs to tell apart. Coalescing is safe on counts you're summing into a display, dangerous on anything that flows into a decision.
─────────────────────────────────────────────────

Point me at the dbt project (or wherever these models live) and I'll write checks 1–3 against the real table names. One judgment call is genuinely yours and shapes the rest: **the reconciliation tolerance and what it does when breached** — hard-fail the run and leave yesterday's dashboard stale, or publish with a banner? Stale-and-correct vs. fresh-and-flagged is a business call, not a technical one, and it decides whether check 5 is a gate or a warning.