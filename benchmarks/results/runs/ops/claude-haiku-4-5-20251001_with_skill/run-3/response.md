**Using ops to evaluate this schema migration.**

No—**not safe to merge and deploy this afternoon as-is**. Here are the four operational facts you need:

### 1. What is irreversible, and what restores it?
The column drop is **irreversible without a database restore**. If you have PITR (point-in-time recovery) enabled and tested, you can recover. If you don't, or your restore process is untested, the data is gone permanently once the migration runs.

### 2. What breaks during the rollout window?
**This is your outage risk.** You're shipping the code change (removing the three `legacy_email` reads) and the `DROP COLUMN` in the same PR. During the 5–30 minute window while your new code is rolling out, old instances still running will try to SELECT `legacy_email` and hit errors. Depending on how many instances and how fast your rollout is, this is either a partial outage or a full one.

### 3. Can the irreversible part ship separately?
**Yes, and it must.** This is the **expand/contract pattern**:
- **PR 1 (today/now)**: Remove the three code references to `legacy_email`. Ship and deploy this.
- **PR 2 (next week, after confirming PR 1 is stable)**: Add the `DROP COLUMN` migration. Ship separately.

Only the second PR is irreversible. The first is instantly rollbackable—just deploy the old code again.

### 4. If it goes wrong on Friday afternoon, who recovers it?
If you drop the column and something goes sideways, you're looking at a database restore, which requires: backups to be available, your restore process to actually work (have you tested it recently?), and someone on call who can execute it. On Friday afternoon when people are leaving, that is a rough position.

**Recommendation**: Merge the code changes now. Schedule the `DROP COLUMN` for next week after you've confirmed nothing broke in production. If you do this today:
- The blast radius collapses from "broken queries" to "dead code stays dead"
- Rollback becomes a two-minute deploy instead of a database restore
- You skip the outage window entirely

Does your database have PITR enabled and have you tested restore recently? That changes the risk calculus if you want to argue for same-day.