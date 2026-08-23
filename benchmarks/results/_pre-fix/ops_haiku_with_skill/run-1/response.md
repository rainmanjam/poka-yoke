**Not recommended.** Based on the analysis from earlier, this couples an irreversible schema change (DROP COLUMN) with a code deploy, which breaks rolling rollback if something goes wrong—and Friday afternoon is the worst time window for that pattern.

**Split the work instead:**

1. **Merge & deploy the code now** (Friday, safe) — the code changes that stop reading `legacy_email` are forward-compatible and reversible. No risk.

2. **Verify no reads overnight** (Friday evening/Saturday) — add a simple query to check if anything still touches that column in production logs or query logs.

3. **Drop the column Monday morning** — after weekend observation, drop COLUMN is a separate, fast migration. If anything breaks, you can roll back the *code* immediately (already live) and keep the *schema* until you fix the reader.

**Why the split matters:**
- Friday evening + schema irreversibility + small deploy window = if a reader you missed is still hitting it, you can't roll back the schema for 2–3 days
- With the split: you get the code live immediately (safe), verify the coast is clear (data-driven), then drop with confidence (Monday morning before business resumes)

The code changes are the small, safe part. The schema change is what's risky on Friday.

Want me to draft the split PRs to make this easier to execute?