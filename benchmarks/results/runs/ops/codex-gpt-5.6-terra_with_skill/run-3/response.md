No—don’t merge-and-deploy the destructive migration as one release this afternoon.

The irreversible step is dropping `legacy_email`; recovery requires a tested snapshot/PITR restore, which you haven’t established. During rollout, old pods, workers, or a rollback version may still read that column and fail once it disappears. Split it: deploy the read-removal code first while retaining the column, then drop the column in a later, explicitly approved migration after confirming no live or scheduled workload references it.

Friday is fine only if the code rollout has a fast rollback owner available. A code rollback cannot restore a dropped column. Green CI and passing tests are useful detection, but they do not make the mixed-version rollout safe.

So: merge/deploy the code-only phase if it contains no `DROP`; hold the column drop for its own release with a verified restore path and deployment gate.