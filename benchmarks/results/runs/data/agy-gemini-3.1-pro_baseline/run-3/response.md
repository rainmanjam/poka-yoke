## Goal Description
The goal is to prevent silent data corruption in the revenue pipeline where upstream schema changes (like a renamed column) result in nulls that are coalesced to 0, causing the dashboard to show plausible but incorrect (low) numbers. 

To answer your question plainly: **No, checking that the revenue table isn't empty is insufficient.** 

The test you added is a shape check that won't catch the actual failure mode. The `COALESCE` to zero is exactly the mechanism that made this failure silent—it took missing data (nulls) and converted it into valid-looking data (0s). Because rows are still being written, the table will never be empty, meaning your test will pass while the data remains silently corrupted. 

A silently wrong number is far more dangerous than a failed pipeline. If the pipeline crashes, you know immediately and can fix it before anyone makes a decision based on bad data. When it fails silently, the business operates on incorrect information—in this case, for three weeks, which is a significant detection gap that needs its own fix.

## Proposed Changes
To properly catch this and prevent it from happening again, we need to implement a series of checks that fail loudly when data is missing, rather than averaging or zeroing it out. 

### Data Contracts / Schema Validation
We must catch upstream changes before they enter the pipeline.
- Implement a **schema check or data contract** on the upstream tables. If an upstream team renames or drops a required column, the pipeline should fail loudly and attributably at the source, rather than propagating nulls.

### Pipeline Assertions (Pre-Publication)
Checks must happen **before** the data is published to the dashboard. Bad data should halt the pipeline so it cannot reach end users.
- Add **null-rate assertions** *before* the `COALESCE` step. If the percentage of nulls in the joined column exceeds a strict threshold (e.g., > 0%), the build should fail.
- Add **volume assertions**. Check that the number of successfully joined rows matches the expected volume based on historical trends.

### Reconciliation against Source of Truth
Shape checks (like "is not empty") only tell us the matrix exists. We need to verify the contents.
- Implement **reconciliation checks** that compare the total revenue in our dashboard table against the upstream source of truth (e.g., total revenue in the billing system). If the numbers don't match, the pipeline should halt.

### Alerting for the Detection Gap
- Set up anomaly detection alerts on the final revenue metric. If daily revenue drops by an unexpected percentage, an alert should fire immediately to the data team, closing the three-week gap where nobody noticed.

## User Review Required
> [!WARNING]
> These changes will shift the pipeline from failing silently to failing loudly. This means the dashboard might be delayed if upstream data is broken, but it guarantees the dashboard will never show incorrect data. Do you approve this shift in strategy?

## Verification Plan
### Automated Tests
- Introduce a mock test where the upstream column is intentionally renamed. Verify that the pipeline fails at the data contract validation step.
- Introduce a mock test where the join produces nulls. Verify that the pre-publication null-rate assertion catches it and halts the pipeline before `COALESCE` happens.
### Manual Verification
- We will manually review the pipeline logs to ensure that the new reconciliation checks are running and correctly comparing totals against the upstream source of truth.