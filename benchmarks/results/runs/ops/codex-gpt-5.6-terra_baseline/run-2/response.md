# Code Review: `legacy_email` removal

## Summary

Don’t deploy the column drop this Friday. The code-only change is fine to merge and ship today; split the irreversible migration into a later, separately observed deployment.

I couldn’t inspect the actual PR here—this workspace only contains benchmark fixtures mentioning `legacy_email`—so this recommendation is based on the rollout shape you described.

## Major

- **Irreversible data loss** — `DROP COLUMN` cannot be undone by reverting code. Recovery requires a tested backup/PITR restore, not merely green CI.

- **Rolling-deploy incompatibility** — old instances can still read `legacy_email` after the schema changes, producing live database errors. A rollback would also restore code that expects a column that no longer exists.

- **Unknown readers** — “three call sites” may exclude workers, ETL/BI queries, exports, other services, or direct database consumers.

## Recommendation

- **Today:** merge and deploy only the code that stops reading the column. Leave `legacy_email` in place; this is normally reversible.
- **After it bakes:** verify production query logs/statement stats and downstream jobs show no reads over a meaningful traffic/job cycle.
- **Next week:** run the drop alone, during staffed hours, with a confirmed and tested restore path.

If you need an intermediate proof, rename the column first; that is quickly reversible and flushes out remaining readers before permanent deletion.