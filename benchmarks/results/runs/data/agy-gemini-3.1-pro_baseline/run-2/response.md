## Goal Description
The current revenue dashboard failed silently for three weeks because an upstream schema change (a renamed column) caused a downstream `JOIN` to return nulls. Because those nulls were being coalesced to `0`, the data appeared correctly shaped but the numbers were just anomalously low.

A test asserting that the "revenue table isn't empty" is **not enough**. When `COALESCE(revenue, 0)` is applied to nulls, the rows are still present—the table won't be empty, it will just contain zeroes. The pipeline will remain "green," and the numbers will remain wrong. In data, **silence is the defect**. We need checks that fail loudly and stop the pipeline when the data is wrong.

## Proposed Changes
To properly catch this failure mode, we need to implement the following checks based on the principles of Poka-Yoke for Data:

### 1. Reconcile Totals (Does it agree?)
The single strongest check for a wrong `JOIN` that produces well-shaped, wrong data is reconciliation.
* **Implementation:** Compare the total revenue sum in the warehouse against the source system's total. If they drift beyond an acceptable margin, fail the pipeline.

### 2. Add Data Contracts at the Boundary
Upstream column renames are the most common cause of pipeline breaks.
* **Implementation:** Declare the expected schema, types, and nullability explicitly on ingest. When a column is renamed, it appears to downstream as a dropped column and an added column. The ingest validation should fail loudly on the missing expected column rather than propagating nulls.

### 3. Quarantine, Don't Coalesce (Is it shaped right?)
Silently dropping or coalescing malformed rows is the data equivalent of `except: pass`. 
* **Implementation:** Instead of `COALESCE(revenue, 0)`, route rows with null revenue (when revenue is expected) to a dead-letter/quarantine table. Set an alert on the rate of quarantined rows so the team is immediately notified when an upstream change breaks the join.

### 4. Volume Checks on Values (Is there the right amount?)
A row count check doesn't catch zeroed-out values.
* **Implementation:** Assert on the actual distribution of the data. For example, check that the sum of revenue or the number of non-zero revenue rows matches historical expectations (e.g., comparing against the same weekday historically, rather than a naive day-over-day check).

### 5. Assertions in the Pipeline
* **Implementation:** These checks must block publication. Build to a staging table, run these tests on staging, and only promote to the final revenue table if they pass. A test that runs after publication and merely emails a warning still lets bad data reach the dashboard.

## User Review Required
> [!IMPORTANT]
> Please confirm if your data warehouse/tooling supports running these tests prior to promoting the table (e.g., dbt tests in a staging phase). 
> 
> Also, what is the authoritative source system we can query to reconcile the final revenue total?

## Verification Plan

### Automated Tests
1. **Simulate Upstream Rename:** Write a test that deliberately renames the upstream column and verify that the pipeline fails loudly at the data contract boundary.
2. **Simulate Null Join:** Feed a mock table with un-joinable keys, and verify that the rows are routed to the quarantine table and that the pipeline promotion fails.
3. **Reconciliation Test:** Inject a discrepancy between the source total and warehouse total, and verify the pipeline halts.

### Manual Verification
* Run the pipeline with a known good dataset and verify it promotes to the dashboard successfully.
* Verify that the dashboard shows `last-updated` so stakeholders know the freshness of the data.