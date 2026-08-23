No — "table isn't empty" wouldn't have caught this, and it's worth seeing exactly why, because the gap tells you what to build instead.

**Why it missed the incident:** the join still produced rows. Nulls got coalesced to 0, so the table was populated, just wrong. "Not empty" is a volume check with the floor set at zero — the weakest possible version of "is there the right amount." You need a check that would actually have gone red.

Two devices would have caught this, and one of them is the strongest tool in the whole class:

1. **Null-rate assertion on the join key, not the output.** The rename didn't break the join loudly — it made the join key stop matching. Assert the match rate (or null rate on the joined column) directly, e.g. "unmatched rows must be <2%." This catches the failure at its source, before the `COALESCE` has a chance to hide it.

2. **Reconciliation: warehouse total vs. source-system total.** This is the one check that validates *logic*, not just shape. A row-count check, a null check, a schema check — all of those can pass on a perfectly well-formed, wrong number. Only "does the sum match the source" catches a join silently dropping data. For a revenue table specifically, this is the check to install first if you only install one.

There's also a design issue independent of tests: `COALESCE(x, 0)` on a join result is doing the same thing as `except: pass` — it converts a loud failure (nulls propagating, dashboard breaking visibly) into a quiet, plausible-looking wrong number. If the null truly can mean "zero legitimately," fine, but then the null-rate assertion above is mandatory, because you've removed your only other signal.

One more structural thing worth checking, separate from what test exists: does this test run *before* the table is published, with the ability to block, or does it run after and just report? A three-week miss usually means the second — worth confirming which one you have, since that ordering matters more than which assertions you write.