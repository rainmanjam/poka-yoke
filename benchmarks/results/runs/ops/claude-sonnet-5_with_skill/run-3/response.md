**Using poka-yoke:ops** — this is a same-deploy schema-drop-plus-code-change, which is exactly the pattern the ops device catalog flags as risky.

**1. What's irreversible, and what restores it?** The `DROP COLUMN` is the irreversible step — once it lands, `legacy_email` data is gone unless restored from a backup, and only for rows that existed at drop time. Nothing in what you described restores it live; a restore is a DB-team operation, not a rollback.

**2. What breaks during the rollout window?** Deploys aren't atomic. If the drop and the code change ship in the same deploy, any instance still running old code mid-rollout (or anything you roll back to) will hit `column does not exist` — a hard error, not a graceful one. That's the actual outage risk, and it's worse on a day with less staffing to catch it.

**3. Can the irreversible part ship separately?** Yes, and it should. Split it:
- **Deploy A (today, Friday-safe):** the three code changes that stop reading `legacy_email`. This is reversible — redeploying old code still works, since the column still exists.
- **Verify:** confirm nothing else reads the column — grep across the org (not just this repo), check query logs for any read in the last month.
- **Deploy B (separate, non-Friday):** the `DROP COLUMN`, once you've watched Deploy A run clean for a bit.

**4. If it goes wrong, who's available?** A code-only revert is a 20-minute fix any time. A dropped-column revert on a Friday evening with reduced on-call is the scenario the "don't deploy destructive migrations on Friday" rule exists for.

**Recommendation:** don't merge this as one PR. Split the column drop into its own PR/deploy, land it on a day when someone's watching. If you want a permanent version of this check rather than remembering it next time, `poka-yoke:guardrails` covers a CI gate that blocks `DROP`/`ALTER...DROP` in a migration unless the PR carries an explicit destructive-change label — want me to set that up?