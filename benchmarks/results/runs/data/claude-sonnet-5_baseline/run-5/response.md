No, that test doesn't catch what actually happened — it's the wrong lens for this failure.

**Why "not empty" missed it:** your incident wasn't a volume problem, it was a **shape problem masquerading as a plausible value**. The join still ran, rows still landed, the table was never empty — nulls got coalesced to 0 and the whole thing sailed through looking like a normal low-revenue period. A row-count check only catches a pipeline that stops producing rows; yours kept producing rows, just wrong ones.

**The check that would have caught this:** reconciliation — does the number agree with an independent source? That's the only one of the four lenses that validates *correctness* rather than *shape*. Row counts, freshness, and schema checks all would have stayed green throughout your three weeks, because nothing about the data's shape changed — only its truth.

Two devices, in order of strength:

1. **Kill the silent `coalesce(x, 0)` on the join.** That's the actual root cause — it's what converted "upstream renamed a column, join now returns null" into "revenue is plausible but low" instead of an error. If a null there is never legitimate, either drop the coalesce and let nulls surface as nulls (or NaN/error) downstream, or replace it with a `CHECK`/assertion: *"if null-rate on this join key exceeds X%, fail the build"* rather than defaulting to zero. This is the Control-rung fix — it makes the specific failure mode structurally impossible, not just detected.

2. **Add a reconciliation assertion**, not just an existence check: compare the revenue total (or row count from the join) against an independent source — the upstream system directly, a finance export, or last week's same-weekday total with a tolerance band. Run it *between load and publish*, so it can block promotion rather than firing an alert after the dashboard's already been live for three weeks. That's the "does it agree?" lens from the skill, and it's the one lens that would have actually caught this — a wrong join produces perfectly well-shaped, non-empty, wrong data.

Also worth checking: is there a **data contract** with the upstream team so a column rename fails ingestion loudly instead of silently producing nulls that your coalesce then hides? That closes the failure at its origin rather than downstream of it.

Want me to help draft the reconciliation check and locate every other `coalesce(..., 0)` in this join path (renames elsewhere are probably hitting the same hole)?