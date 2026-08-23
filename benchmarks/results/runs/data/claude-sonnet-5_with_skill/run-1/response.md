Using **poka-yoke:retro** + **poka-yoke:data** — this is an incident (retro decides what to fix) that broke in a pipeline (data decides which device).

**No.** A non-empty check doesn't touch the actual failure mode. During the whole three weeks, the table was never empty — the row count was fine. What broke was that a `NOT NULL` join value silently became a valid-looking `0`. Your test asserts volume; the incident was in reconciliation. It would have passed every single day of the outage. That's the "check that cannot fail" pattern this repo's own CLAUDE.md calls out — before trusting it, you'd want to prove it actually goes red against this incident, and it doesn't.

**The three things, separated:**
- **Defect**: dashboard understated revenue for 3 weeks, caught only at finance close.
- **Mistake**: upstream renamed a column; the join started missing; nothing surfaced that.
- **Hazard**: `COALESCE(revenue, 0)` makes "no match" and "zero revenue" indistinguishable. That's the real target — the coalesce, not the missing test.

**Devices, ranked by rung (data's four questions: is it there / right amount / shaped right / does it agree):**

1. **Control** — stop coalescing the join result. Either let the null propagate and fail the build on any NULL in a required revenue column post-join, or replace the silent `COALESCE(revenue, 0)` with something that can't produce a plausible wrong value — a sentinel that fails downstream, or a `NOT NULL` constraint on the joined column before it's allowed to be zero.
2. **Warning/gate** — assert join match-rate (e.g. `null_rate` on `revenue` pre-coalesce) is ~0, and block promotion to the published table if it isn't. This is the one that would have fired on day one of the rename.
3. **Detection, but the right kind** — a **reconciliation** check: warehouse revenue total vs. the source system's total, within tolerance, daily. Row count wouldn't have moved during this incident; the total would have.
4. **Boundary** — a data contract on the upstream table so a column rename breaks loudly (or quarantines) instead of silently producing nulls that get zeroed.

Your row-count test is still worth keeping — it's real Detection-rung coverage for a different failure mode (partial load, filter that matches nothing) — just don't let it stand in for the check that would have actually caught *this* incident.

Two decisions I need from you before I write these: what reconciliation tolerance is acceptable (exact match vs. some %), and what should happen when the null-rate gate trips — block the pipeline, or quarantine the unmatched rows and publish the rest?