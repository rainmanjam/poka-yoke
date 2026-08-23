No — hold off on merging this as a single change, and definitely don't drop the column this afternoon. Running the skill's four questions on it:

1. **What's irreversible, what restores it?** The `DROP COLUMN` itself. Unless you have a tested PITR/backup restore, the answer is "nothing" — once it's gone, getting `legacy_email` back means a database restore, not a revert.
2. **What breaks during rollout?** If this ships as one deploy and something's wrong post-merge, your rollback is "restore the column from backup," not "redeploy the previous commit." That's a much slower, riskier recovery path than a code-only change would need.
3. **Can the irreversible part ship separately?** Yes, and it should. This is the textbook expand/contract case: the three code call-sites reading `legacy_email` are the reversible part; the `DROP COLUMN` is the irreversible part. Bundling them means you can't get the safety of the reversible step without also committing to the irreversible one.
4. **If it goes wrong Friday afternoon, who's around and how fast is rollback?** Even a small, well-tested change deployed Friday afternoon means any restore work lands in a thinner-staffed window.

Concretely, I'd split it:
- **Today (if you want to ship something):** merge just the code changes that stop reading `legacy_email`. That's reversible in minutes via normal revert-and-redeploy — genuinely fine for a Friday.
- **Separately, next week:** confirm nothing else (reports, backfills, other services) still reads the column, then run the `DROP COLUMN` as its own deploy with people around to react.

Green CI here doesn't cover this risk — tests won't tell you whether a restore path exists or how long it takes. If you want, I can help split the diff into the two PRs, or draft the CI guard mentioned earlier in this session that blocks `DROP`/destructive `ALTER` from landing alongside application code, so this can't recur.