I'd advise **against** deploying the DROP COLUMN today. Here's why:

Looking back at the analysis from earlier this session: dropping the column couples an irreversible schema change with a code deploy, which breaks rolling rollback. If the deploy has issues on Friday afternoon, you can't roll back — the column is already gone, and rolling back the code but not the schema creates a mismatch.

**Safer Friday approach:**
- ✅ Merge and deploy the **code changes only** today (reading the three places that use `legacy_email`)
- ⏸️ Hold the `DROP COLUMN` for Monday

**Why this works:**
- Code-only deploys roll back cleanly (no schema state to reconcile)
- Monday, after verifying nothing reads the column over the weekend, you safely drop it
- If issues surface Friday, you roll back code and the column still exists for any emergency fallback
- You get the Friday win (code deployed, old references removed) without the Friday risk

The column rename → drop sequence (which I'd outlined earlier) takes a bit longer but is even safer if you want maximum caution.

If you want me to draft a split PR (code now, schema Monday) so you're not managing two commits manually, I can do that. Otherwise, just skip the ALTER TABLE from today's merge.