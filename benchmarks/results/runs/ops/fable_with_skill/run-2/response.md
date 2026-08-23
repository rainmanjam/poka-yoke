Read both. The `ops` skill is self-contained for this question, so here's the answer in the shape it prescribes — the four questions first, then the recommendation.

## The four things you need to know before shipping

**1. What's irreversible, and what restores it?**
The `DROP COLUMN legacy_email` is the irreversible step. Once it runs, the data in that column is gone — a code revert does not bring it back. What restores it is a database backup taken *before* the migration, and only one that someone has actually restored from. If you can't name when your backup was last restored (not taken — restored), treat the column's contents as unrecoverable when you weigh this.

**2. What breaks during the rollout window?**
This is the part "small change" hides. The PR bundles the schema drop with the three code updates. Deploys aren't atomic: for some window, old pods/instances still running the previous code will issue `SELECT ... legacy_email` against a table where the column no longer exists. Every one of those queries errors. Whether that's a blip or an outage depends on how long the old code lingers and whether those three read paths sit on a hot route — but it is a real error window, not a risk, and CI can't see it because CI never runs old code against the new schema.

**3. Can the irreversible part ship separately?**
Yes, and it should. This is textbook expand/contract — you're at the *contract* step, which is the one that gets its own deploy:

- **Deploy A (today, fully reversible):** the three code changes only. Code stops reading `legacy_email`; the column stays. If anything's wrong, `git revert` and redeploy — minutes, no data at stake.
- **Deploy B (next week, after A has soaked):** the `DROP COLUMN`. By then nothing references it, there's no rollout window problem, and you've confirmed in production that the three edits were really the *only* three readers — you can check logs/query stats for any surviving reads of the column, which CI can't tell you either.

**4. Who's around, and how fast is rollback?**
Deploy A rolls back in the time it takes to redeploy the previous image. Deploy B rolls back via a restore, which is hours and needs the people who know the restore procedure. The Friday question is really: is the restore path staffed this afternoon and over the weekend? For A it doesn't matter. For B it does.

## Recommendation

Merge and deploy the code half this afternoon — that's a genuinely small, reversible change and Friday is fine for it. Split the `DROP COLUMN` into its own PR and run it once the code change has been in prod long enough to prove no other reader exists.

Two devices worth adding so this decision doesn't rest on someone remembering next time (ops skill → `guardrails` for the mechanics):

- **CI gate (Warning rung):** fail any PR whose changed migrations contain `DROP`, `TRUNCATE`, or `ALTER ... DROP` unless it carries an explicit `destructive-migration` label — and reject the label on PRs that also touch application code, which mechanically enforces the split.
- **Restore drill on a schedule (makes the drop reversible):** a timed restore into a real environment. Until one has happened, "we have backups" is a belief, not a device.

**Recap:** CI green is true but irrelevant to the two actual risks — the rollout window where old code reads a dropped column, and the data being unrecoverable without a proven backup. Ship the code edits today; ship the drop next week as its own PR after checking prod for stray readers. If you want, I can draft the migration-gate CI check for this repo's `guardrails` pattern.