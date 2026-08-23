No. A non-empty table would still pass when every joined revenue value is `NULL` and then coerced to `0`.

Treat missing revenue as an error, not a zero:

- **Schema contract upstream:** fail when the required column is missing/renamed or changes type.
- **Join-quality assertion:** require a high match rate; alert/fail if unmatched rows or null joined revenue exceed a tiny, explicit threshold.
- **No silent coalescing:** preserve `NULL` as “unknown”; only convert to `0` where a business rule proves zero is valid.
- **Reconcile totals:** compare dashboard revenue to the source-of-record / finance ledger, with a defined tolerance.
- **Plausibility monitors:** alert on sharp drops in revenue, join coverage, row counts, freshness, or distributions—even if the table is populated.
- **Pipeline test data:** include a deliberately renamed/missing join key and assert the job fails loudly. Run it once broken and confirm the check goes red.

The crucial invariant is: “all expected revenue-bearing records successfully map to a valid revenue value,” not merely “the revenue table contains rows.”