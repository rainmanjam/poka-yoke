## Goal Description
The current solution (checking that the revenue table isn't empty) is not enough. It is a very weak "Detection" device (Rung 3) that only catches a complete 100% data failure. Since the issue was a column rename that caused a join to return nulls which were then coalesced to 0, the table was not empty—it just contained bad data that looked plausible. We need to implement devices that prevent silent failures and convert them into loud, pipeline-blocking errors.

## User Review Required
> [!IMPORTANT]
> The most critical change is removing the blind `COALESCE(..., 0)` on the upstream revenue column. This will cause the pipeline to fail (or quarantine rows) when data is missing, rather than silently padding with zeros. This means your dashboard might be delayed instead of wrong, which requires stakeholder alignment.

## Open Questions
> [!WARNING]
> 1. Do we have the ability to enforce a **Data Contract** with the upstream team so their schema changes break at ingest rather than downstream?
> 2. Does our current warehouse/scheduler support a "Write-Audit-Publish" pattern (e.g., building to a staging table, testing, and only swapping to the live table if tests pass)?
> 3. Can we query the upstream source system directly to perform a reconciliation check (comparing source total vs. warehouse total)?

## Proposed Changes

### 1. Data Contracts and Schema Validation at the Boundary (Warning / Rung 2)
The root cause was an upstream schema change (column rename). 
- **Change:** Implement a schema validation step on ingest. If the expected column is missing, the ingest job must fail immediately.
- **Why:** This catches the renamed column *before* it reaches the join, turning a silent downstream data issue into a loud, attributable upstream contract breakage.

### 2. Remove Blind Coalescing and Enforce `NOT NULL` (Control / Rung 1)
Coalescing unexpected nulls to 0 hid the error.
- **Change:** Remove `COALESCE(revenue_column, 0)`. If the revenue column is fundamentally required for a row to be valid, enforce a `NOT NULL` constraint on the table, or add a pipeline assertion that the null rate is exactly 0%.
- **Why:** If the join fails to find a match, the row will evaluate to NULL. A `NOT NULL` constraint will physically reject the write (Control), preventing the defect.

### 3. Volume and Distribution Checks (Warning / Rung 2)
An "is not empty" check is too weak.
- **Change:** Implement a volume check that compares today's row count and total revenue sum against the *same weekday historically* (e.g., within 10% of the same day last week).
- **Why:** Business data is weekly-seasonal. A drop of 80% because of a bad join will trigger this check immediately, even if the table isn't completely empty.

### 4. Write-Audit-Publish Pattern
- **Change:** Assertions (null checks, volume checks) must run *between* load and publish. Build the revenue table in a staging schema, run the checks, and only promote/swap to the live dashboard schema if all checks pass.
- **Why:** A test that runs after publication lets bad data reach the dashboard. A blocking pipeline test ensures the dashboard either shows yesterday's good data (with a stale warning) or today's good data, but never today's bad data.

### 5. Reconciliation (Detection / Rung 3)
- **Change:** Add a check that aggregates the total revenue in the warehouse and compares it to the total revenue reported by the upstream system for the same time period.
- **Why:** This is the ultimate safety net. Even if the schema is right and the rows are not null, a logic error in a `JOIN` (e.g., fanning out or dropping rows) will cause the totals to drift.

## Verification Plan

### Automated Tests
- Introduce a mock upstream schema change (e.g., rename the column in a dev environment) and verify that the pipeline fails at ingest, *before* producing zero-revenue rows.
- Introduce a mock join failure and verify that the `NOT NULL` constraint or staging tests block the publish step.

### Manual Verification
- Review the modified SQL models to ensure `COALESCE` is only used for genuinely optional data, not as a blanket error-swallower.
- Verify that a pipeline failure triggers an alert rather than silently proceeding.