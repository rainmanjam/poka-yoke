## Goal Description
The objective is to mistake-proof the revenue pipeline against silent failures. A recent incident allowed wrong (low) revenue numbers to reach the dashboard for three weeks because an upstream column rename caused a join to return nulls, which were masked by a `COALESCE(col, 0)`. The current mitigation—a test ensuring the table is not empty—is insufficient because it only checks if data exists, not if the values are correct or if the total volume matches expectations.

We need to implement devices that convert silent wrongness into loud pipeline failures.

## User Review Required
> [!IMPORTANT]
> The recommendations below represent a shift from "always produce a number" to "fail loudly if the number might be wrong". Please review whether your pipeline architecture supports blocking deployment to production on test failure (e.g., Write-Audit-Publish pattern).

## Open Questions
> [!WARNING]
> To provide exact code implementations, I need to know:
> 1. What tools are you using for transformation and testing (e.g., dbt, Great Expectations, SQL mesh)?
> 2. Do you have access to the source system totals to implement a reconciliation check?

## Proposed Changes

Based on the `poka-yoke` data guidelines, a simple "not empty" check is not enough. Here is the plan to layer defenses, from strongest (Control/Warning) to informative (Detection).

### 1. Reconcile totals against the source system (Does it agree?)
This is the single most important device for financial data. A structural logic error (like a bad join) can produce perfectly shaped, non-empty data that is completely wrong.
* **Device**: A daily check that compares the total revenue in the warehouse against the source of truth (e.g., Stripe, billing DB).
* **Rung**: Detection (or Warning if run before publish). This guarantees that dropped rows or coalesced zeroes are caught immediately because the totals will drift.

### 2. Validate schemas at the boundary (Data Contracts)
The root cause was an upstream schema change (a rename). 
* **Device**: Treat upstream as untrusted. Assert the expected schema, types, and column names on ingest.
* **Rung**: Warning/Control. If a column is renamed, the pipeline should fail *before* the join even runs, explicitly stating that the contract was broken.

### 3. Remove blind `COALESCE` or assert before it (Is it shaped right?)
The `COALESCE(col, 0)` masked the failure, turning nulls into plausible zeroes.
* **Device**: If the column is fundamentally required for a row to be valid, do not `COALESCE`. Use a `NOT NULL` constraint or assertion. If nulls *are* sometimes expected but 100% nulls indicates a break, add a null-rate assertion on the raw column *before* the coalesce.
* **Rung**: Warning.

### 4. Implement seasonal volume bounds (Is there the right amount?)
A `count > 0` test is too weak (a floor of 1). The incident data wasn't empty, it was just low.
* **Device**: Assert both a floor and a ceiling based on historical seasonality (e.g., total row count or revenue sum should be within 10% of the same day last week).
* **Rung**: Warning.

### 5. Block the pipeline on failure (Assertions in the pipeline)
* **Device**: Tests must run *before* the data reaches the dashboard. Write to a staging table, run the reconciliation and volume tests, and only promote/swap to the production table if they pass.
* **Rung**: Elevates Detection to Control/Warning.

## Verification Plan
1. **Simulate a rename**: Temporarily rename the source column in a dev environment and verify the pipeline fails at the ingest step.
2. **Simulate a bad join**: Intentionally break the join condition in dev and verify the reconciliation check and seasonal volume bounds catch the discrepancy before the table is promoted.