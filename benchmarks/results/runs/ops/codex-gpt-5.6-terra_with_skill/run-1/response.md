No—don’t deploy the column drop this afternoon as part of the same release.

- **Irreversible:** `DROP legacy_email` destroys data. Restore requires a tested snapshot/PITR path; none was established here.
- **Rollout risk:** any old web instance, worker, scheduled job, or rollback binary that still reads it will fail after the migration.
- **Split it:** deploy the read-removal first, confirm all old processes are drained and no production queries reference the column, then schedule the drop as a separate contract release.
- **Friday is fine only if:** a named responder is available, rollback is proven for the code release, and the database restore path is tested. A schema drop itself cannot be rolled back by redeploying code.

CI and tests are useful detection, but they don’t prove the rollout window or restore path. I also couldn’t verify this PR from the current workspace—the visible diff is unrelated benchmark work and contains no `legacy_email` references.

For a durable guardrail, make CI block destructive migrations unless an explicit approval gate confirms the prior read-removal release has already been deployed.