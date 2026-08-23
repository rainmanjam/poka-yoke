## Goal Description
The goal is to safely remove the `legacy_email` column and update the three places in the code that read it, without causing an outage or data loss, especially considering it's a Friday afternoon.

## User Review Required
> [!CAUTION]
> **This PR will cause an outage if merged and deployed as-is.**
> Co-deploying a destructive schema change (dropping a column) with the code that stops depending on it is a guaranteed outage, not a risk.

Here is the analysis based on the `ops` mistake-proofing principles:

1. **What here is irreversible, and what restores it?**
   Dropping the `legacy_email` column is irreversible. Reverting the code will not put the column back. Restoring it requires restoring from a database backup, which takes time and loses any data written since the backup.
2. **What breaks during the rollout window?**
   During the deploy, the old code is still running against the new database schema. The old code will try to read the dropped `legacy_email` column and crash. 
3. **Can the irreversible part ship separately?**
   Yes. The code that removes the dependency on `legacy_email` must ship in a separate deploy *before* the schema migration that drops the column. This follows the final step of the "expand and contract" pattern.
4. **If it goes wrong, who is available and how fast is rollback?**
   It's Friday afternoon. Rollback is not a simple git revert—it requires a database restore, which is slow and requires people who might be offline.

## Open Questions
> [!IMPORTANT]
> How would you like to proceed? We should split this into two separate PRs.

## Proposed Changes
Instead of one PR, we must split this into two separate deployments:

### PR 1: The Reversible Code Change
#### [MODIFY] The 3 files reading `legacy_email`
Update the code to stop reading `legacy_email`. Since the column is still in the database, this deploy is safe and reversible. If anything breaks, you can instantly roll back the code.

### PR 2: The Irreversible Schema Change (Contract)
#### [DELETE] `legacy_email` column in migration
Once PR 1 is fully deployed and you confirm no traffic is hitting the old code paths, ship the database migration to drop the column. Do this next week, not on a Friday afternoon.

## Verification Plan

### Automated Tests
* Run existing test suites for PR 1 to ensure the code works without `legacy_email`.

### Manual Verification
* Monitor error rates during PR 1 rollout.
* Verify logs/metrics to ensure the 3 places in the code are completely clear of traffic before merging PR 2.