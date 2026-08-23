**Not yet — you need to answer the four critical ops questions first.** The ops skill identifies schema migrations as inherently risky during deployments, and Friday deploys need stronger devices than a "small change" assumption provides.

Before you ship, establish these explicitly:

### 1. **What here is irreversible, and what restores it?**
Dropping `legacy_email` is irreversible. What's your restore path if the rollback needs data? (e.g., backup, PITR window, nothing)

### 2. **What breaks during the rollout window?**
You're deploying code that doesn't read `legacy_email` AND dropping the column in the same change. For the 5–15 minutes while old code is still running:
- If a running instance of version N tries to read `legacy_email`, it will error
- Is version N still running anywhere during your deploy, or are all instances cut over atomically?

### 3. **Can the irreversible part ship separately?**
The ops pattern for schema migrations is **expand/contract** — separate deploys:
- **Deploy 1** (this week): Update the three code paths to stop reading `legacy_email`. Leave the column. Deploy, verify, keep it running for a day or two.
- **Deploy 2** (next week): Drop the column in a separate migration. If this fails, you can revert; the data is still there.

Can you split this into two deploys, or is there a constraint preventing it?

### 4. **If it goes wrong, who is available and how fast is rollback?**
On Friday afternoon, if the deploy breaks:
- Who is on-call with prod access?
- How long to rollback? (If it's "restore from backup", that's hours, not minutes.)
- Can you revert the code + re-add the column in < 10 minutes, or does the migration need a manual restore?

**If you can answer all four and the blast radius is genuinely low, then yes. If you can't, or if the rollback is slow, this should ship Monday with one of your team at the keyboard.**