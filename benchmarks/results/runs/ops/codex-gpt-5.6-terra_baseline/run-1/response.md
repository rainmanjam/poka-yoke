Don’t deploy the column drop this afternoon as a single change. A dropped column is a destructive schema migration, even if only three application reads remain.

Merge is reasonable if the PR separates the rollout:

1. Deploy the code that no longer reads `legacy_email`.
2. Confirm every running consumer is on that version—workers, cron jobs, integrations, BI/ETL, admin scripts, and rollback images.
3. Monitor production successfully.
4. Drop the column in a later, separately reversible release.

Green CI proves the tested code paths, not unversioned consumers or an emergency rollback path. On a Friday, I’d merge the compatibility change, but schedule the actual column removal for a staffed window unless you have verified dependency inventory and a tested database restore/rollback plan.