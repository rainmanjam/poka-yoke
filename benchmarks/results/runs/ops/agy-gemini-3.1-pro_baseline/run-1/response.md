## Goal Description
The PR aims to remove the `legacy_email` column and update the three places in the code that read it. 

However, we must sequence this deployment safely to avoid an outage.

### Critical Assessment
1. **What here is irreversible, and what restores it?** Dropping the `legacy_email` column is irreversible; recovering from a mistaken drop requires restoring from a database backup or point-in-time recovery.
2. **What breaks during the rollout window?** Deploys are not atomic. During the rollout window, old application code runs against the new database schema. Any instances that haven't been replaced yet will crash when they try to query the dropped column.
3. **Can the irreversible part ship separately?** Yes, we must split the reversible code change from the irreversible column drop.
4. **If it goes wrong, who is available and how fast is rollback?** Since it is Friday afternoon, team availability is lowest over the weekend. A code rollback takes minutes, but an irreversible database drop rollback takes hours of database restoration.

## User Review Required
> [!WARNING]
> **Do not merge this PR as-is.**
> Green CI proves the *final* state works, but it does not test the rollout window. Co-deploying a destructive schema change with the code that depends on it is guaranteed downtime.

## Open Questions
- Do we have tested backups or point-in-time recovery enabled for this database in case an emergency restore is needed?
- Are you comfortable splitting this into two PRs and delaying the actual column drop until Monday?

## Proposed Changes

We will use the **Contract** phase of the Expand/Contract pattern.

### PR 1: Ignore the Column (Deploy Today)
Update the application code to stop reading from the `legacy_email` column. 
- **Blast Radius:** Low.
- **Reversibility:** Fully reversible. If the new code breaks, rolling back the deployment instantly reverts to the old code, which still finds the column intact.

### PR 2: Drop the Column (Deploy Monday)
Create a new migration to execute `DROP COLUMN legacy_email`. 
- **Blast Radius:** High (irreversible).
- **Why Monday?** The entire team will be available if we discover a secondary system (like an external analytics pipeline) was secretly relying on the column.

### Systemic Protections
#### [NEW] CI Pipeline Checks
Add a CI gate that fails the build if a PR contains both application code changes and destructive DDL (like `DROP COLUMN`).

## Verification Plan

### Automated Tests
- Verify CI passes for PR 1 (code change only).
- Test the new CI gate by opening a PR with both a code change and a `DROP COLUMN` migration to ensure it fails.

### Manual Verification
- Deploy PR 1 and monitor error rates to ensure the new code functions correctly without `legacy_email`.
- Next week, deploy PR 2 (schema drop) during core hours.