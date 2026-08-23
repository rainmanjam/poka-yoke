Short answer: merge the code half today, don't drop the column today. Not because it's Friday — because the two halves have different reversibility and you've stapled them together.

I'm reasoning from your description; this repo isn't the one with `legacy_email`, so tell me the repo/PR if you want me to check the actual diff.

**1. What's irreversible, and what restores it?** `DROP COLUMN` destroys the values. Reverting the PR restores the *code*, not the data. The restore path is a PITR/snapshot restore into a scratch DB plus a backfill join — hours, several people, and only if someone has actually restored that backup recently. If nobody has, treat the data as unbacked.

**2. What breaks during the rollout window?** Deploys aren't atomic. For a few minutes old pods run against the new schema and every query touching `legacy_email` errors. If you use an ORM where the column is on the model, that's not three code paths — it's every `SELECT` on that table, including ones the three call sites never touch.

**3. Can the irreversible part ship separately?** Yes, and it's the standard split. The code change (stop reading the column) is fully reversible and safe to ship anytime. The `DROP` is the contract step and belongs in its own deploy, after the read-removal has run in prod long enough to prove nothing else wanted it.

**4. Who's around, and how fast is rollback?** Code-only revert: minutes, one person. Post-drop recovery: hours, multiple people, on a Saturday.

The thing worth sitting with: **green CI is not evidence the column is unused.** It proves your test suite doesn't read it. It cannot see raw SQL strings, BI/dbt models, another service on the same database, a nightly export, or an admin report. Those are exactly where a dropped column surfaces — days later, silently, as an empty field rather than an error.

Concrete plan:

- **Today:** split the PR. Ship the code-only change removing the three reads. Reversible, deployable Friday, fine.
- **Before dropping:** turn "I think it's unused" into a measurement — grep the whole org for the string (not just this repo), and check `pg_stat_statements` / query logs for a week for any statement naming the column.
- **Next week, own deploy:** snapshot immediately prior, then drop.

★ Insight ─────────────────────────────────────
The Friday question is a proxy for the real one: *how long does recovery take, and who's awake?* A two-minute revert is fine on Friday at 4pm. That's why splitting the PR actually answers the question rather than dodging it.
─────────────────────────────────────────────────

Want me to write the CI guard that blocks a destructive `ALTER`/`DROP` from landing in the same PR as application code? That's the device that makes this split automatic instead of remembered.