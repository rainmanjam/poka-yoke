**Short answer: don't merge it as one PR, and don't drop the column this afternoon regardless.**

Per the `ops` mode, the four questions that matter here:

1. **What's irreversible, and what restores it?** The `DROP COLUMN` is the irreversible step. Restore path = a database backup/snapshot restore — assuming one has actually been *tested*, not just taken. If nobody's run a restore drill on this table recently, treat the data as effectively unbacked. If someone later needs `legacy_email` (support ticket, audit, backfill you didn't know about), it's gone.

2. **What breaks during the rollout window?** This is the real risk, not the drop itself. A deploy isn't atomic — for a window, old pods/processes are still running against the new schema. If the column drops before every instance is running the code that stopped reading it, those old instances start erroring on every request that touches that path. That's your Friday-afternoon outage, not the migration.

3. **Can the irreversible part ship separately? Yes, and it should.** You already have the reversible half and the irreversible half stapled together:
   - **Reversible**: the code changes that stop reading `legacy_email` in the three places.
   - **Irreversible**: the `DROP COLUMN`.
   
   Ship the code-only change today. Deploy it. Let it run — that's your real verification that nothing still depends on the column (grep isn't enough; check query logs / APM for reads against it over the next few days). Then drop the column in its own migration, its own PR, its own deploy.

4. **If it goes wrong, who's around?** A code revert is a 20-minute fix any day of the week. A dropped column that turns out to matter needs a DB restore, ideally with someone who knows the restore procedure awake and available. Friday afternoon is a bad time to need that person.

**So: merge and deploy the code-only change this afternoon if you want — that part is genuinely low-risk and reversible.** Hold the `DROP COLUMN` for its own deploy, preferably not Friday afternoon, after you've confirmed nothing in prod is still touching the column.

Want me to help split the diff — pull the migration into its own PR and check what CI guard would catch a bundled drop+code-change PR like this automatically (`ops` mode has a device for that)?