No—don’t deploy the combined code-and-drop migration this afternoon.

- The irreversible step is `DROP COLUMN legacy_email`; reverting application code will not restore its data. Proceed only with a verified, tested restore/PITR path.
- During rollout, old workers, queued jobs, rollback artifacts, or another service can still query the column and fail as soon as the schema changes.
- Split it: deploy the read-removal first, let it run through a full rollout window, verify production has zero column references, then schedule the drop as a separate explicitly approved migration.
- Friday is fine only if the destructive step has a tested restore path and an available owner who can execute it. CI and unit tests don’t establish either.

I also couldn’t inspect the stated PR itself in this checkout—there is no application migration or `legacy_email` reference here, only benchmark fixtures—so I can’t independently validate the “three places” claim. Merge the non-destructive read-removal portion if it is independently deployable; hold the column drop.