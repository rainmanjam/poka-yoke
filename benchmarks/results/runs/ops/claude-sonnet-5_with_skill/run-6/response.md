Not as one deploy, no. Here's why, applying the ops framework:

**1. What's irreversible, and what restores it?**
The `DROP COLUMN` is the irreversible step. Unless you have a recent backup or snapshot you could restore from, once it drops, `legacy_email` data is gone — CI passing tells you nothing about this, since tests don't measure "can I get this back." Say explicitly whether you have a tested restore path; if not, that's the single most important fact here.

**2. What breaks during the rollout window?**
Deploys aren't atomic. While this rolls out, old instances (and anything else that reads that column — replication, an analytics job, a downstream service you don't own) can still be running against the schema after it's dropped. That's the real risk, not the change itself. "Three places in the code that read it" is only the places *you* found in *this* repo — worth checking whether anything outside it touches the column too.

**3. Can the irreversible part ship separately?**
Yes, and it should. Split this into expand/contract:
- **Deploy 1 (today, if you want):** update the three call sites to stop reading `legacy_email`. This is reversible — the column still exists, so rolling back the deploy is enough if something's wrong.
- **Deploy 2 (separately):** drop the column, once you've confirmed nothing anywhere still reads it.

Shipping the drop stapled to the code change means if anything unexpected still depends on that column, you find out via a hard failure with no easy way back.

**4. If it goes wrong, who's around?**
This isn't superstition about Fridays — it's about recovery speed. The code-only deploy is fine this afternoon since it's a two-minute revert. The `DROP` is the part I'd hold until Monday morning, when someone's actually watching and can act fast if a consumer you didn't know about breaks.

**Recommendation:** don't merge this as one PR on the strength of green CI. Split it — ship the read-site changes now if you like, hold the column drop for a separate, later deploy with people watching. Longer term, worth a CI gate that blocks any `DROP`/`ALTER...DROP` in a migration unless the PR carries an explicit destructive-change approval label (that's `guardrails` territory if you want me to help set it up).