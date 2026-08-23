I'd hold off on the deploy part, even though merging the PR itself is probably fine.

The risk isn't the code — it's that dropping a column is one of the few operations here that isn't cheaply reversible. If a background job, BI query, or read replica still touches `legacy_email` outside the three call sites you found, "CI green + tests pass" won't catch it, and un-dropping a column means restoring from backup, not just reverting a commit.

Safer sequencing: merge and deploy the code that stops *reading* the column today (that part's trivially revertible by redeploy). Hold the actual `DROP COLUMN` migration for Monday, after the code's had a full business day to prove nothing unexpected breaks — Friday afternoon buys you a weekend of reduced eyes if it does.