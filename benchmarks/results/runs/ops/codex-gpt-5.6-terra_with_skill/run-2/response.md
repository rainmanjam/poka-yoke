No—don’t deploy the column drop bundled with the code change this afternoon.

- The irreversible step is `DROP legacy_email`; only a proven backup/PITR restore can recover it, and none is stated.
- During rollout, an old worker, canary, queued job, or rollback may still read the column and fail.
- Split it: deploy the code that no longer reads `legacy_email` while retaining the column; verify every production version/job is clear, then drop it in a later, explicitly approved migration.
- Friday is fine only if the reversible deploy has an on-call owner and a fast rollback. A column drop is not made safe by green CI or a small diff.

Before the eventual contract migration, require a mechanical “no remaining reads” check plus an explicit destructive-migration gate.