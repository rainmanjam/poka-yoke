Short answer: split it, and don't run the `DROP` itself this afternoon.

**What's irreversible, and what restores it?** The `DROP COLUMN` is the irreversible step. The restore path is "point-in-time recovery / a full backup restore" — not something you'd want to reach for on a Friday evening if it turns out something still needed that data. If you don't currently have a tested restore for this DB, treat the column as gone-for-good the moment it drops.

**What breaks during the rollout window?** Deploys aren't atomic. If the column drop and the code change land in the same deploy, there's a window where old pods/instances (still running the code that reads `legacy_email`) can hit the DB after the column is already gone — that's a live error, not a hypothetical. Green CI and passing tests don't cover this, because tests don't exercise "old code, new schema" during a rolling deploy.

**Can the irreversible part ship separately?** Yes, and it should:
1. Ship the code-only change today — remove the three reads. This part is fully reversible (git revert + redeploy) and is genuinely a safe Friday change.
2. After that's deployed and confirmed stable (no errors, no lingering reads in logs/APM for `legacy_email`), grep the wider org/other services for any consumer of that column you don't control from this repo (BI tools, read replicas, cron jobs, other services hitting the same DB directly).
3. Run the `DROP COLUMN` as its own deploy, separately.

**If it goes wrong, who's around, and how fast is rollback?** This is the actual reason to not run the drop itself this afternoon — if you drop it at 4pm Friday and something unexpected reads it, your rollback is a DB restore, on a weekend, with reduced coverage. The code-only deploy has a two-minute rollback (revert). The drop does not.

So: merge and deploy the code changes now if you want, that's Friday-safe. Hold the actual `DROP COLUMN` for Monday, after you've confirmed nothing outside this PR's three call sites still touches `legacy_email`.

If you want, I can help write that verification grep/query and a CI guard that blocks `DROP`/destructive `ALTER` from landing in the same PR as app code, so this split becomes automatic going forward.