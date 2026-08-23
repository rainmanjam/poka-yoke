No. A non-empty revenue table would still pass in the failure you described: rows existed, but joined revenue was `NULL` and then silently converted to zero.

Add devices that fail on the actual bad states:

- **Join coverage assertion:** require a high match rate for the upstream key (for example, `matched_rows / source_rows >= 99.5%`), with an explicit, reviewed exception list.
- **No silent null-to-zero:** prohibit `COALESCE(revenue, 0)` on values derived from required joins. Treat missing revenue as an error or separately label it `unknown`, never as zero.
- **Schema contract:** assert the required upstream column exists and has the expected type before the transformation runs.
- **Reconciliation:** compare dashboard revenue to an independent source or prior-stage total; alert/fail when variance exceeds a defined threshold.
- **Distribution/anomaly check:** flag abrupt drops in join-match rate, zero-revenue share, or total revenue versus recent comparable periods.
- **Positive control:** deliberately rename/remove the join column in a test fixture and prove every relevant check fails.

The invariant should be “revenue is complete and explainable,” not merely “the table has rows.”