## Goal Description
Conduct a Poka-Yoke retro and implement preventative devices for the recent revenue dashboard incident. The incident occurred because an upstream team renamed a column, causing a join to return nulls, which were silently coalesced to 0 for three weeks. The proposed plan moves beyond the currently implemented "not empty" test to address the systemic hazard.

## User Review Required
> [!WARNING]
> The current "not empty" test you added **would have passed** during this incident. Because the pipeline coalesced nulls to 0, the table was populated with rows, just with $0 revenue. A "not empty" check does not catch zeroed-out data.

> [!IMPORTANT]
> The fixes proposed here will require changing how the pipeline runs (e.g., building to staging first, or failing the pipeline on schema drift). Please review these architectural changes.

## Open Questions
- What data warehouse and pipeline tool (e.g., dbt, Airflow, Snowflake) are you using? This will determine the exact syntax for the constraints.
- Do we have access to the source system's total revenue to set up a reconciliation check?

## Proposed Changes

Following the `retro` and `data` Poka-Yoke skills, we separate the incident into three parts:
- **The defect:** Revenue was reported incorrectly (low) for three weeks.
- **The mistake:** Upstream renamed a column, breaking our join.
- **The hazard:** The pipeline silently accepted a missing upstream column, and `COALESCE` acted as a silent `except: pass`, masking the missing data.

Here is the implementation plan to install devices from strongest (Control) to weakest (Detection).

### 1. Ingest Data Contracts (Control)
We must catch the missing/renamed column at the boundary, before it reaches the join.
- **Action:** Implement a schema validation check on the raw source table.
- **Device:** If the expected revenue column is missing or changes type, the pipeline must **fail and quarantine** the run immediately. A rename must be treated as a breaking change, not a silent null.

### 2. Pipeline Assertions (Warning / Control)
The pipeline must stop if the data is malformed, rather than pushing bad data to the dashboard.
- **Action:** Assert the null-rate of the raw joined column *before* the `COALESCE` is applied. 
- **Device:** Build the data to a staging table. Run a test that asserts `COUNT(revenue_col) / COUNT(*) > 0.99` (or whatever threshold is appropriate). Only promote the staging table to production if this test passes. 

### 3. Reconciliation Check (Detection)
A check for "not empty" only verifies volume, not correctness.
- **Action:** Implement a reconciliation query.
- **Device:** "Does it agree?" Compare the total revenue sum in the warehouse against the source billing system. This is the only check that catches logic errors (like a bad join) even when the schema is perfectly valid.

### 4. Class Sweep
A poka-yoke that fixes one call site is not a poka-yoke. We need to find everywhere else this hazard exists.
- **Action:** Audit the codebase for other instances of `COALESCE(col, 0)` on upstream joins that feed critical or financial metrics, where a missing column would be silently masked.

## Verification Plan

### Automated Tests
- Run the pipeline against a mock upstream table where the column has been renamed. Verify that the pipeline **fails** at the ingest contract stage, rather than succeeding with 0s.
- Verify the null-rate assertion fails the staging build if we manually inject nulls.

### Manual Verification
- Review the class sweep results to ensure all similar `COALESCE` hazards are identified and ticketed.
- Verify the reconciliation check accurately flags a deliberate 1% discrepancy.