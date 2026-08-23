## Goal Description
The goal is to safely stop reading from and subsequently drop the `legacy_email` column.

## User Review Required
> [!CAUTION]
> **Order-dependent migration hazard (M7)**
> We cannot merge and deploy this PR as written. Dropping a column in the same deployment as the code change that stops reading it will cause an outage. During the rollout window, older instances of the application will still be running and will crash when they try to query the `legacy_email` column that has already been dropped from the database schema.

## Proposed Changes
We must use the **expand/contract** pattern. Instead of a single PR, this change must be split into two separate deployments:

### Phase 1: Stop Reading (PR 1)
- Update the three places in the code to stop reading the `legacy_email` column.
- **Merge and deploy this change first.**

### Phase 2: Drop Column (PR 2)
- After Phase 1 is fully rolled out (meaning no old code is running), create a second PR that contains the database migration to `DROP COLUMN legacy_email`.
- **Merge and deploy this change.**

### Device: CI Gate (PR 3)
- To prevent this from relying on human memory in the future, we should add a CI check that blocks destructive DDL (like `DROP COLUMN`) from co-deploying with application code changes. 

## Verification Plan

### Automated Tests
- Ensure the test suite passes for PR 1 against a database that still has the `legacy_email` column.

### Manual Verification
- Wait for PR 1 to finish deploying completely before merging PR 2. 
- Ensure that the proposed CI gate correctly rejects PRs that contain both code changes and destructive DDL.