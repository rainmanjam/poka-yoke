The `ops` skill doesn't point at additional reference files, so I have what I need. Here's the answer.

## Short answer: not as one PR this afternoon. Split it, ship the code half today, drop the column next week.

Taking the skill's four questions in order:

**1. What's irreversible, and what restores it?**
The `DROP COLUMN legacy_email` is the irreversible step. `git revert` brings the code back; it does not bring the data back. What restores it is a backup or point-in-time recovery — and only if someone has actually *restored* from it, not just taken it. If you can't name the last successful restore drill, treat that column's data as unbacked for this decision. A revert-tested code change and an untested backup are very different "small changes".

**2. What breaks during the rollout window?**
This is the real problem, and green CI can't see it. Deploys aren't atomic: for some window, the *old* code — the version that still reads `legacy_email` in three places — runs against a schema where the column is gone. Every one of those three paths errors on a missing column until the last old instance cycles out. Worse, if the migration runs first and the deploy then fails or gets rolled back, you're left with old code, no column, and no way back except restore. CI passed because tests run new code against new schema; that combination never exists during a rollout.

**3. Can the irreversible part ship separately?**
Yes, and that's the fix. Expand/contract:

- **PR A (today is fine):** remove the three reads. Nothing drops. Old and new code both work against the unchanged schema, so rollback is a plain revert. Merge and deploy this afternoon without worry.
- **PR B (next week):** `DROP COLUMN`, once you've confirmed nothing references it in prod — including things tests don't cover: reporting queries, ETL jobs, ad-hoc scripts, ORM models that `SELECT *`. It gets its own deploy and its own approval.

**4. If it goes wrong, who's around and how fast is rollback?**
For PR A: revert in minutes, no staffing concern. For the combined PR: recovery is a database restore, and Friday afternoon is exactly when the people who'd run it are leaving. The Friday rule isn't superstition; it's a question about recovery time versus who's awake, and "small diff" doesn't change the recovery time of a dropped column.

## The device, so this isn't a conversation next time

This answer is rung 0 (training) unless you install something. Two options, highest first:

- **Control:** a CI check that fails any migration containing `DROP`, `TRUNCATE`, or `ALTER ... DROP` unless the PR carries an explicit `destructive-migration-approved` label — so a code change and a column drop physically cannot land in the same unlabelled PR. The `guardrails` mode in this plugin has the gate shape.
- **Warning** (if you don't want to block): a bot comment listing every destructive statement in changed migrations, so the reviewer sees the drop named rather than skimming past it.

Either way, prove the check fails before trusting it — open a PR with a `DROP` and no label, watch it go red.

**Recap:** Don't merge the PR as-is. Split it: the three code changes are safe to ship today; the column drop is irreversible, breaks old instances mid-rollout, and belongs in its own deploy after you've verified a working backup restore. Then add a CI gate so destructive migrations can't hitch a ride on code PRs again.