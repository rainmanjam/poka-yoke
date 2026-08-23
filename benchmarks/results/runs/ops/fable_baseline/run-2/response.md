The `gh` call was blocked and this repo (a plugin/skills repo) doesn't contain a `legacy_email` column anyway, so I'll answer from what you've described rather than the diff.

**Short answer: don't merge-and-deploy as one step this afternoon.** Not because it's Friday — because a column drop bundled with the code that stops reading it is the one migration shape where "CI green, tests pass" tells you almost nothing.

**Why the green CI is misleading here**

Tests run against a fresh schema with the new code. Production doesn't deploy like that. During a rolling deploy there's a window where:

- the migration has run (column gone) but old pods/instances are still serving traffic and still `SELECT legacy_email` → hard 500s on every affected query until the rollout finishes; or
- the migration runs *after* the rollout, which works — until the deploy fails halfway and you have new code on a schema that still has the column (harmless) but a half-applied migration queue.

And the part that's actually irreversible: **`DROP COLUMN` destroys the data.** If one of the "three places that read it" was miscounted — a raw SQL string, a report, an ORM `select *` that a serializer depends on, a downstream ETL, a reporting replica — you find out Saturday, and the rollback is a restore-from-backup, not `git revert`.

**The safe shape (expand/contract)**

1. **PR 1 (today, fine to ship Friday):** the code changes only. Stop reading `legacy_email`. Leave the column. Deploy. Fully reversible with a revert.
2. **Wait** a cycle — a few days, over whatever batch jobs / weekly reports you have — and confirm nothing is still touching it. If you have query logs or DB statement stats, that's your device: grep for `legacy_email` there, not just in the repo.
3. **PR 2 (next week, mid-week morning):** `DROP COLUMN`. Take a backup / snapshot immediately before. Now the drop is safe because nothing can break.

If you genuinely need the drop soon, the halfway option is to *rename* the column (`legacy_email` → `legacy_email_dropped_2026_08`) in PR 2 — anything still reading it fails loudly, and the rename reverts in seconds. Drop it a week later.

**Before PR 1, two quick checks worth doing:**
- `grep -rn legacy_email` across *every* repo/service that talks to that database, not just this one — plus any SQL in dashboards, dbt/ETL configs, and fixtures.
- Confirm the PR's migration isn't auto-run on deploy. If it is, split the migration out of the PR now.

So: merge the code half this afternoon if you like; hold the `DROP` until it can be reverted by something cheaper than a restore.