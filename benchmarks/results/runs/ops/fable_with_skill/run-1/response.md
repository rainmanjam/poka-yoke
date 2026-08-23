Following the `ops` mode: the four questions first, then the recommendation.

## Short answer: merge the code half today, don't drop the column today

**1. What's irreversible, and what restores it?** The `DROP COLUMN` is the irreversible step. The three code changes are reversible in one `git revert` — the column drop is not. What restores it: a backup that has actually been *restored* recently, or point-in-time recovery. If you can't name the last time someone restored a backup of this database, treat the column's data as gone the moment the migration runs.

**2. What breaks during the rollout window?** Deploys aren't atomic. If the migration runs before every old pod/instance is replaced, the old code still executes `SELECT ... legacy_email` against a table that no longer has it → 500s on every request that touches those three code paths. That window — not the change itself — is the outage. "Small change" describes the diff, not the blast radius; ask what fraction of traffic the three readers serve, because that's the real number.

**3. Can the irreversible part ship separately?** Yes, and this is the fix. Expand/contract says the contract step (the drop) is its own deploy, after nothing references the column. Your PR staples steps 4 and 5 together. Split it:

- **PR A (today is fine):** only the three code changes. Column stays. Fully reversible — rollback is a redeploy.
- **PR B (next week):** `DROP COLUMN legacy_email`, after A has been live long enough that logs/error tracking confirm no reader is left — including anything the "three places" grep missed: raw SQL, ORM `SELECT *` serializers, reporting queries, ETL jobs reading the warehouse replica.

**4. Who's around, how fast is rollback?** PR A rolls back in minutes with whoever's on-call. PR B done Friday afternoon rolls back only via restore, with a partial weekend crew. Friday isn't superstition; it's that question 4 has a bad answer for the drop and a fine one for the code.

## Green CI is not evidence here

CI proves the new code works against the new schema. The failure mode is old code against the new schema, which no test exercises. That's the check-that-cannot-fail pattern this repo warns about.

## Devices so this doesn't rely on you remembering next time

| Rung | Device |
|---|---|
| **Control** | CI check that fails any changed migration containing `DROP`/`ALTER … DROP`/`TRUNCATE` unless the PR carries an explicit `destructive-migration` label — see `guardrails` mode. |
| **Control** | Deploy order enforced: migrations run only after the code rollout completes (or the drop is gated behind "no instances older than N"). |
| **Warning** | Migration runner prints the table, column, and row count and requires typed confirmation for destructive DDL. |
| **Detection** | A restore drill on a schedule, so "we have backups" is a measured fact. |

**Recap:** Merge and deploy the three code reads this afternoon; pull the `DROP COLUMN` into a separate PR for Monday or later, and gate destructive migrations in CI so the two halves can't be co-deployed again. If you paste the migration file and the deploy config I can check the rollout ordering and write the CI gate.