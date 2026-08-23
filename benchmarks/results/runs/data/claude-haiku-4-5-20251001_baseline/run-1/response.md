Not quite — and this is exactly the pattern your CLAUDE.md warns about.

A "revenue table isn't empty" check is like the detector that reported `{"count": 0}` for both a clean scan *and* for scanning nothing. It's not a device yet; it's a rumor. Here's why:

**Your actual failure mode:** upstream renamed a column → join returned NULLs → coalesced to 0 → table still had rows, numbers just looked low. Your "not empty" test would have passed through all of that.

**What you need instead:**

1. **Positive control**: Verify the join specifically produces the revenue values you expect, not just that rows exist. Something like `SELECT COUNT(*) FROM revenue WHERE revenue_amount > 0` or a query that checks the distribution isn't suspiciously skewed to zero.

2. **Break it on purpose**: Rename the upstream column in your test data, run the check, watch it fail. Then restore it. A check that's never gone red is a rumor.

3. **The near-miss**: Add a test case where the join silently produces NULLs (simulating the column rename) and verify that coalescing masks it. That's the failure mode you want to catch — not emptiness, but **plausible but wrong numbers**.

Example shape:
```sql
-- Positive: revenue amounts are non-zero and match upstream
SELECT COUNT(*) as non_zero_revenue 
FROM revenue 
WHERE revenue_amount > 0;
-- Should fail if join is broken (would show 0)

-- Near-miss: explicitly test the coalesce case
-- Simulate a join that returns nulls, verify it doesn't silently look OK
```

Run the near-miss with the broken join and confirm it catches the problem. That's when you'll know it's a device, not a test.

What does your current test schema look like? I can help you shape the actual check.