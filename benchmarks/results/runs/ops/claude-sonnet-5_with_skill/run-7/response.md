Applying the `ops` mode framework here — this is exactly the "drops a column" + "Friday" pattern it's built for.

**1. What's irreversible, and what restores it?**
The `DROP COLUMN` itself. Once it runs, `legacy_email` data is gone unless you have a very recent backup — and restoring means restoring the *whole table/database* to a point in time, not just the column, which is its own operation with its own risk. If you haven't checked, don't assume a backup exists and is restorable — an untested backup is a belief, not a device.

**2. What breaks during the rollout window?**
Deploys aren't atomic. If the migration runs before every instance of the old code is off, or if anything else — another service, a report, an analytics job, a support tool — still reads `legacy_email` that you haven't found, it breaks the moment the column disappears, not when you notice. "The three places I updated" is a claim about what you found grepping the app code; it says nothing about jobs, replicas, or external consumers.

**3. Can the irreversible part ship separately?**
Yes, and it should. This is a textbook expand/contract case — you're doing steps 1–4 and step 5 (the actual `DROP`) all in one deploy. The safer shape:
- Ship the three code changes (stop reading the column) today, if they're otherwise safe.
- Let that sit — ideally through a full traffic cycle, so you've observed nothing breaks with the column merely unused.
- Drop the column as its own deploy, separately, once you're confident.

Splitting it costs you a second small PR and buys you the ability to fix "oops, something else needed it" by editing code instead of restoring a database.

**4. If it goes wrong, who's around and how fast is rollback?**
This is the real Friday-afternoon question — not "is the change small" but "if this breaks at 4:45pm, is someone available to notice and fix it before Monday?" Rolling back the code deploy is fast; rolling back a dropped column is not reversible by deploy at all — only by data restore.

**Bottom line:** the code changes are fine to ship this afternoon. The `DROP COLUMN` is not something size or CI-green tells you is safe — those verify correctness, not reversibility. If you split it as above, ship the code today and schedule the drop for a day next week when you can watch it. If you want to drop the column today anyway, at minimum confirm you have a tested (actually restored, not just taken) backup and that someone's around for the next couple hours.

Want me to look at the actual migration/PR diff to check for the other hazards in this list — untested backup, other readers of the column, whether the drop is separated from the code change?