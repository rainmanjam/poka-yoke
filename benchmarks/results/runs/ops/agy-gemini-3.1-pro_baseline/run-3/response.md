## Goal Description
The goal is to safely remove the `legacy_email` column and the three places in the code that read it.

## User Review Required
> [!CAUTION]
> **Do not merge and deploy the current PR as-is, especially on a Friday afternoon.**
> 
> Co-deploying a destructive schema change with the code that depends on it is a guaranteed outage, not a risk. During the deployment window, the migration will drop the column while the old version of the code is still running and trying to read it. This will cause the old code to crash until the new code fully rolls out.
> 
> Furthermore, dropping a column is an irreversible operation. If we need to roll back, reverting the code will not bring the column (or its data) back. Restoring from a backup could take hours and require staff who may be unavailable on a Friday afternoon.

## Proposed Changes
We must split the current PR into two separate deployments following the **Expand and Contract** pattern.

### PR 1: Update the code
Update the three places in the code so that nothing references `legacy_email` anymore.
- Deploy this PR first.
- This is a reversible change. If something breaks, we can easily roll back the code.

### PR 2: Drop the column
Only *after* PR 1 is fully rolled out and we are certain no code is referencing `legacy_email`, create a second PR with the schema migration to drop the column.
- Do not deploy this on a Friday. Deploy it next week during regular hours when full staffing is available, just in case a restore is needed.

## Verification Plan

### Manual Verification
1. **Before PR 1**: Ensure you have a tested backup of the database in case of any accidental data loss.
2. **After PR 1**: Verify through logs and monitoring that no queries are attempting to access `legacy_email`.
3. **Before PR 2**: Confirm the blast radius (who is affected if this fails) and establish the exact time it would take to restore the database from backup if the column drop causes unforeseen issues.