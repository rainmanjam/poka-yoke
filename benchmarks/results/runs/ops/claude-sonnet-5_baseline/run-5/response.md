Short answer: merging the code changes is probably fine; running the actual `DROP COLUMN` this afternoon is where I'd slow down.

**Main risk:** dropping a column is a one-way door. If someone finds a problem over the weekend, you can revert the code deploy in seconds — but you can't un-drop a column without a restore. The standard mistake-proofing move here is expand/contract: merge and deploy the code that stops reading `legacy_email` now (fully reversible), let it bake a few days, then run the drop migration separately on a normal weekday when people are around to catch fallout.

One thing worth checking before either step: does anything outside the three call sites read `legacy_email` — background jobs, analytics/ETL exports, other services, read replicas? "Grep found three, tests pass" proves the app layer is clean, not that nothing else touches the column.

Is the `DROP COLUMN` migration bundled in this same PR/deploy, or is it a separate step? That changes what I'd recommend.