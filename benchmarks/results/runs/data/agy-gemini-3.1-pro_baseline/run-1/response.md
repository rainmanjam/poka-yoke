## Goal Description
The goal is to address a silent failure in the revenue pipeline where an upstream schema change (column rename) resulted in null values, which were then coalesced to `0`. A check for table emptiness was added, but we need to evaluate if this is sufficient and plan robust checks that follow the project's *poka-yoke* principles to ensure the pipeline fails loudly when data is missing or corrupted.

## User Review Required
> [!IMPORTANT]
> Based on the repository's rules (specifically "absent data does not raise"), checking that the table isn't empty is **not enough**. 
> 
> Because your pipeline coalesced the nulls to `0`, the resulting table was full of rows with `0` revenue. An "is not empty" check will look at this broken table and pass it, because the table *isn't* empty—it's just wrong. You have built a check that cannot fail under the exact conditions that caused the incident.

## Open Questions
> [!WARNING]
> 1. **Why are we coalescing to 0?** If a missing record or null value is an error state, defensive `COALESCE` statements often hide the error. Should we drop the coalesce and let the nulls trigger a failure?
> 2. **What transformation framework are you using?** (e.g., dbt, Airflow, raw SQL) This determines how we implement upstream schema contracts.

## Proposed Changes
To truly mistake-proof this pipeline, we need to implement devices that will catch the failure at the source and verify the data's integrity.

### 1. Enforce Upstream Schema Contracts
The root cause was an upstream column rename. You need a device that fails *before* the join executes.
- **Action:** Add a schema test on the upstream source table to assert the required column exists and has the correct type. If the column is renamed, the pipeline stops immediately.

### 2. Remove Defensive Coalescing (Fail Loudly)
- **Action:** If nulls in this join are always a sign of a broken contract, remove `COALESCE(revenue, 0)`. Add a test that asserts `revenue IS NOT NULL`. This makes the missing data fail loudly instead of averaging out to a plausible zero.

### 3. Assert Meaningful Data, Not Just Presence
Instead of checking for row count > 0, check that the data behaves as expected.
- **Action:** Add an aggregate threshold check (e.g., `SUM(revenue) > [Historical Minimum]`) or check that known-good dimensions (like key regions or customer segments) have non-zero revenue.

## Verification Plan

### Automated Tests
As stated in the repo's guidelines, a check that has never gone red is a rumor.
1. **The near-miss:** Run the pipeline with valid data to ensure it succeeds.
2. **Break the instrument:** Temporarily rename the upstream column in your development environment.
3. **Verify the failure:** Run the pipeline and assert that your new checks *fail the build*. If they pass, the check is still broken. Put the column name back.

### Manual Verification
Review the pipeline execution logs to confirm that the schema validations run as a blocking step *before* the transformation runs.