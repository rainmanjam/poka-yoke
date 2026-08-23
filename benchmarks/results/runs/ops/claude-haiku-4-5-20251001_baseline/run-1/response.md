I see a couple of things worth checking before Friday afternoon, given the context:

**Database migration safety**: Dropping a column is a data operation that's trickier than code changes. Even with CI green, I'd verify:
- **Backward compatibility during rollout** — if old code briefly runs alongside new, does it handle the missing column gracefully? (Or are you doing a coordinated deploy?)
- **Rollback plan** — if production fails, can you restore the column quickly, or restore from backup?

**Timing context**: The startup hook mentions a recent double-charge incident and ongoing SOC2 audit. Friday afternoon deploys can be risky if something goes sideways and your team isn't fully present for troubleshooting. Is this:
- Low-risk data cleanup (column never actually used in weeks)?
- Critical for compliance or an incident follow-up (worth the risk)?

**Questions for you**:
1. What's your on-call coverage tonight/weekend if something breaks?
2. Is the column definitely dead (grep confirms nothing reads it after your changes)?
3. Did you test the deploy path itself (staging deploy, or dry-run)?

If it's truly a small, low-risk cleanup and you have confidence in rollback, green CI/tests, and coverage tonight — you know your system better than I do. But "small change" + "Friday afternoon" + recent production incidents is a flag I'd raise. What's the downside of merging now and deploying Monday morning?