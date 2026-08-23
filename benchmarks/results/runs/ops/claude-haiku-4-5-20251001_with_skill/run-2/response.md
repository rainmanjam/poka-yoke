**Don't merge this yet.** The skill says to answer four questions first, and this one fails the fundamental test:

### The four ops questions

1. **What is irreversible?** Dropping `legacy_email`. Restore path: a database restore from backup (1–4 hours depending on your setup, plus someone awake to run it).

2. **What breaks during rollout?** If you deploy the code that stops reading it, but your old code (canary/partial rollout) hasn't drained yet, old instances will fail trying to read a column that's now gone. That's a 500-rate spike during deploy.

3. **Can the irreversible part ship separately?** **Yes.** This is the entire point of the expand/contract pattern. Your current PR is the "contract" step — the irreversible one. It should not live in the same deploy as the code changes.

4. **Rollback on Friday afternoon?** If something goes wrong post-deploy, you're either redeploying old code (which fails, because the column is gone), or restoring a backup (takes hours, needs people). That's the worst possible moment.

### The fix

**Ship two PRs:**

1. **This PR (code changes only)** — remove the three places that read `legacy_email`. Leave the column untouched. Deploy it. Wait a few days and confirm nothing is still reading it.

2. **Second PR (drop the column)** — after the first deploy has been live, in a separate deploy, drop `legacy_email`. This is reversible via backup but does not risk an outage because no code reads it.

This follows the expand/contract pattern the skill describes — the column drop is step 5 of 5, and it gets its own gate and deploy. It's not Friday-afternoon risky anymore; it's Friday-next-week safe.

The skill also notes there's a CI guard for this: a check that blocks any `DROP COLUMN` unless explicitly approved. Worth installing if you don't have it.