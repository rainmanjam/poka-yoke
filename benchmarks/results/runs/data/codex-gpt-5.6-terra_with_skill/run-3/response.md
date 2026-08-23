No. An “is the revenue table empty?” test protects only against total absence. Your failure still had rows and plausible zeros.

- Defect: revenue dashboard understated for three weeks.
- Mistake: an upstream rename made a required join key null; `COALESCE(..., 0)` converted “unknown/unmatched” into “zero.”
- Hazard: the pipeline can publish revenue with failed joins and no reconciliation.

Install these devices, in order:

1. **Source control:** a versioned schema/data contract. A rename or removal of the required column must be a breaking change that fails consumer ingestion—not a nullable surprise.

2. **Publish-blocking warnings:** build to staging and refuse promotion when:
   - the required upstream column is missing or has the wrong type;
   - required join-match rate falls below its expected threshold (often 100%, with explicit exceptions);
   - the raw joined revenue is unexpectedly null;
   - join cardinality changes unexpectedly.

   Run these before any `COALESCE`. Preserve “unmatched” as a distinct state; only coalesce values that are genuinely allowed to be zero.

3. **Reconciliation detection:** compare dashboard revenue against the source-of-record total for each reporting period. This is the critical backstop for revenue, because a join can be structurally valid yet logically wrong.

Also add freshness and historical volume bounds, but treat them as supporting checks, not the primary defense.

Prove the device works: deliberately rename the upstream column in a test fixture and show the staging pipeline blocks publication; then show a genuine zero-revenue row still passes. Finally, sweep other money/metric pipelines for joins followed by `COALESCE(..., 0)`—the same silent hazard is likely elsewhere.