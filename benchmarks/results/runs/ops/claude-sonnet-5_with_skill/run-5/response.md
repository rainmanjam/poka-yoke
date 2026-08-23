Straight answer: don't ship the drop this afternoon — the "column drop" and "code that no longer reads it" are two different risk profiles stapled into one PR, and Friday is the wrong day for the risky half.

Running the four questions the `ops` skill asks first:

1. **What's irreversible, and what restores it?** The `DROP COLUMN legacy_email` step. Once it runs, the data is gone from the live table — restoring it means a database restore (backup or point-in-time recovery), not a code revert. If you don't know when the last backup was *restored* (not just taken), treat this as unrecoverable.
2. **What breaks during the rollout window?** This is the real question, not the drop itself. Deploys aren't atomic — for some period, old pods/instances are still running against the new schema (or vice versa, depending on deploy order). If *anything* still reads or writes `legacy_email` that isn't one of "the three places" you found — a background job, a different service, an analytics/ETL pipeline, a read replica, a cached query plan — it errors the moment the column disappears, and you won't know until it does.
3. **Can the irreversible part ship separately?** Yes, and it should. Split it:
   - PR A (now): stop reading/writing `legacy_email` in those three places. Deploy, let it run in production for a while (days, not hours) to prove nothing else touches the column.
   - PR B (later, not Friday): the actual `DROP COLUMN`, once A has been live long enough to be confident.
4. **If it goes wrong, who's around and how fast is rollback?** For PR A, rollback is a normal revert. For PR B, there is no rollback once the drop runs — only a restore. Asking "can I deploy this afternoon" is really asking "am I comfortable initiating an irreversible action right before the weekend, with fewer people watching if something surfaces at Friday-night traffic."

Recommendation: merge and deploy the code-change half today if you want — that part's reversible and fine for a Friday. Hold the actual column drop for a day when you can watch it land and have someone around, after you've confirmed (grep across all services, not just this repo, plus check for any read replicas/ETL) that nothing else references `legacy_email`.

If you want, I can help you split the current PR into those two, or write a quick check for any remaining references to the column outside this repo's three call sites.