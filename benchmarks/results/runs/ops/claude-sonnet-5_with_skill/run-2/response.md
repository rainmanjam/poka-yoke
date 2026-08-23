Using **poka-yoke:ops** since this is a schema-migration deploy question — same one flagged earlier in this session.

Straight answer: **no, not as one PR, and not on a Friday afternoon.** The four things that matter here:

1. **What's irreversible, and what restores it?** `DROP COLUMN legacy_email` is the irreversible step. Once it runs, the data is gone unless you can restore from a backup/PITR snapshot — and that restore would also roll back every other row change since the drop, not just this column. If you haven't named a restore path, treat it as "nothing restores it."

2. **What breaks during the rollout window?** This is the part that actually bites. Deploys aren't atomic — during a rolling deploy (and especially if you need to *roll back*), old pods running the previous code will still try to read `legacy_email` from a table where it no longer exists. That's a hard crash on read, not a graceful failure, and it happens exactly when you're most likely to need a fast rollback.

3. **Can the irreversible part ship separately? Yes — and it should.** This PR bundles two unrelated risk profiles:
   - Removing the three read sites → fully reversible, revert-in-minutes, fine to ship any day including Friday.
   - `DROP COLUMN` → irreversible, and rollback of *this* step means restoring from backup, not `git revert`.

   The standard device here is expand/contract: ship the code change first, confirm in production that nothing reads the column anymore (logs, error tracking, a day or two of runway), *then* drop the column in its own deploy.

4. **If it goes wrong Friday afternoon, who's around and how fast is rollback?** For the code-only change, rollback is a redeploy — safe any time. For the DROP, "rollback" isn't a redeploy, it's a database restore, which is not a Friday-afternoon-with-skeleton-crew operation.

**Recommendation:** split the PR. Merge and deploy the three code changes today if you want — that part's genuinely low-risk. Hold the `DROP COLUMN` for a separate PR/deploy earlier in the week, after you've confirmed via logs/query monitoring that nothing (including any downstream jobs, not just app code) is still touching `legacy_email`.

If you want, I can also sketch the CI guard from `poka-yoke:guardrails` that blocks a `DROP`/`ALTER...DROP` from merging unless the PR is explicitly labeled as an approved destructive change — that turns this from a judgment call into a device.