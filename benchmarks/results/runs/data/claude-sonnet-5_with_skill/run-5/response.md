No — that test can pass on exactly the data that just cost you three weeks. A revenue table with every row present but silently coalesced to 0 is still a non-empty table. The check can't fail on the failure you actually had; it's the same "check that cannot fail" shape this repo's own CLAUDE.md calls out for the hazard detector.

Running the four questions from `poka-yoke:data` against what happened:

- **Is it there?** Yes — that's what your test covers. Not the bug.
- **Is there the right amount?** Row count was fine. Also not the bug.
- **Is it shaped right?** Individually, each `0` is a perfectly valid revenue value. Not the bug either — that's what makes coalesce-to-0 dangerous: it manufactures well-shaped data.
- **Does it agree?** This is the one that breaks. The join silently dropped matches, so the warehouse total stopped agreeing with the source system's total. That's the only lens that catches a logic error the data still *looks* fine after.

So the mistake isn't "we didn't test enough," it's that **the join can null out on a rename and the pipeline has no way to notice** — the coalesce is doing exactly its job (avoid a crash) while destroying the one signal (`NULL`) that would have said something broke.

Devices, strongest rung first:

1. **Control — stop the coalesce from hiding the break.** If that join key is supposed to always match, don't `COALESCE(revenue, 0)` blindly. Either assert the null rate on the joined column before the coalesce and fail the build, or add a contract check on the upstream table's schema (expected columns present, by name) that fails loud the moment a rename lands — treat a rename as drop+add, not a compatible change.
2. **Warning — reconciliation, not row-count.** Add an assertion comparing this table's revenue total to the upstream source total (or row-match-rate on the join). This is the one that would have actually caught your incident, because it's the only check sensitive to a wrong join that still produces "valid" rows.
3. **Ordering matters as much as the check.** Whatever you add needs to sit *between* load and publish and be able to block promotion — not run after and email someone. A detection-only test that fires after the dashboard is already live is what let this run three weeks.

What stops this from being full Control: most warehouses can't enforce "this column's null rate must be zero" as a write-time constraint, so the join-integrity check ends up as Warning (pipeline-blocking assertion) rather than Control (physically can't happen) — worth saying explicitly rather than calling a test "prevention."

Want me to look at the actual join/model and draft the null-rate + reconciliation assertions for it?