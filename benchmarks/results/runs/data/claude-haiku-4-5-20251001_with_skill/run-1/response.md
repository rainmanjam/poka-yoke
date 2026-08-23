**Subject: Revenue dashboard reconciliation gap** — you're using a Detection device (a test running after bad data exists), and it only catches the "completely empty table" failure mode, not the silent wrongness mode (nulls coalesced to zeros). That test is insufficient.

Here's what your incident maps to using the four questions:

| Question | What happened | Your test | Gap |
|----------|---------------|-----------|-----|
| **Is it there?** (freshness) | Data arrived fine | Not checked | If the pipeline stalled, you wouldn't notice |
| **Is there the right amount?** (volume) | Table had rows, just wrong values | Checks `COUNT(*) > 0` | Passes even when values are zeros from coalesce |
| **Is it shaped right?** (schema) | Upstream renamed a column | Not checked | No validation on schema contract; the join failed silently |
| **Does it agree?** (reconciliation) | **This is where it failed** | Not checked | **This is what you need** |

Your test catches zero-row failure (the loudest defect). What it misses: a join that returns nulls is silently wrong data — exactly the failure mode you hit. Adding an "is not empty" test doesn't prevent a repeat because the revenue rows would still exist (filled with zeros).

**What to install instead, in order of rung:**

1. **Data contract (Warning)** — Validate the upstream schema on ingest. When they rename a column, your load quarantines the bad batch and alerts before it reaches the dashboard. This requires schema validation + dead-letter routing, not a test after publication.

2. **Reconciliation assertion (Warning)** — Compare the warehouse total against the authoritative source (your billing system, Stripe API, wherever the true revenue lives). A revenue table that disagrees with its source is loud. This is the device that would have caught your coalesce-to-zero scenario immediately.

3. **Null rate assertion (Warning)** — Assert that revenue columns have <X% nulls. Your coalesce converted nulls to 0, but if you'd asserted "revenue column must be >99% non-null", the spike would have triggered before anybody made decisions.

4. **Volume over time (Detection)** — Day-over-day volume check that compares to the same weekday historically (your revenue was 3 weeks low; a naive day-over-day check would have cried wolf every Monday, so compare to last week's same day). Combined with reconciliation, this catches drift.

**The ordering matters.** Your current test runs after data is published. Per the data skill: "The check must stop the pipeline — a test suite that runs after publication and emails a failure lets bad data reach the dashboard." Build to staging, assert in staging, promote only on pass.

Do you want to implement reconciliation first (highest value for revenue), or should you tackle the data contract (prevents the upstream rename scenario from happening again)?