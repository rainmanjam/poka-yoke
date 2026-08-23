No. A non-empty-table test would likely have passed during this incident: rows still existed, and `COALESCE(..., 0)` turned missing join results into plausible revenue values.

The hazard is: the pipeline can treat “unknown because the join broke” as “real zero revenue,” then publish it.

Keep the non-empty check, but add these as blocking checks on the staging model before dashboard publication:

- A source data contract: required upstream column, type, and version must be present. A rename fails ingestion instead of becoming nulls. This is a **Warning** device; a producer-side versioned contract/gate is closer to **Control**.
- A join-integrity assertion before any `COALESCE`: `unmatched_join_count = 0` (or an explicitly agreed, tightly bounded exception rate). Never turn join-generated nulls into zero without recording and checking the reason.
- A reconciliation: compare dashboard revenue to an independent source-of-truth aggregate for the same period, with a small defined tolerance. This is the check most likely to catch a well-shaped but logically wrong join.
- Volume/cardinality guards: historical weekday-aware row and revenue floors/ceilings, plus uniqueness checks on the revenue grain. These catch partial or fan-out joins.

Build → validate staging → promote only on pass. If validation fails, retain the last known-good published table and visibly mark it stale rather than publishing zeros.

Prove each device can fail: rename the source column, create an unmatched key, and alter the source total; each should block promotion. Also verify that a legitimate zero-revenue row still passes.