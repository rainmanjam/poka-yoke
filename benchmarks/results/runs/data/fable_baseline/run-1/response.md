No. The "not empty" test would have passed every one of those three weeks — the table wasn't empty, it was full of plausible zeros. A check that couldn't have caught the incident isn't a regression test for it.

Here's the incident as a chain of silences, and what each one needs:

**1. The rename produced nulls instead of an error.** A `SELECT` against a missing column should fail; a join key that's suddenly absent didn't because the engine happily matched nothing. Device: a **schema contract** on the upstream table — assert the columns you depend on exist with the types you expect, *before* the model runs. In dbt that's a `source` with declared columns plus a `dbt-expectations` `expect_table_columns_to_match_set` (or just a `not_null` on the join key in the source). This is the one that makes a rename loud on day one instead of day twenty-one.

**2. `COALESCE(x, 0)` turned "unknown" into "zero".** That's the data equivalent of `except: pass` — it converts a missing value into a plausible one. Device: remove the coalesce on the revenue path, and put a **null-rate assertion** on the joined column (e.g. `< 1%`). If some nulls are legitimate, quarantine those rows to a dead-letter table with a reason and alert on the rate; don't silently make them zero.

**3. Nothing compared the total to reality.** Shape checks can't catch a wrong join that produces well-shaped wrong data. Device: a **reconciliation test** — sum of revenue in the mart vs. sum in the source/billing system for the same window, within a tolerance. This is the only check in the list that catches *logic* errors, and it's the one to install if you install only one.

**4. The check, even if it existed, had to be able to stop publication.** A test that runs after the dashboard refreshes and emails someone is Detection after the damage. Build to staging → run tests → promote only on pass. Same tooling, different ordering.

**5. Volume drift.** Optional but cheap: revenue-per-day compared to the same weekday over the prior N weeks, alert on >X% drop. This would have fired on day one as "revenue is low" — vaguer than the above, but it's the backstop for the failure you haven't thought of yet.

Honest rung assessment: in most warehouses all of these are **Warning/Detection**, not Control — the bad row can still be written. The thing that gets you closest to Control is the schema contract at the boundary, because it fails before any wrong number exists.

And prove it: temporarily rename the column in a dev copy, run the tests, watch them go red, put it back. A check that's never failed is a rumour.

If you want, point me at the model and I'll draft the contract, the null-rate test, and the reconciliation query against your actual column names.