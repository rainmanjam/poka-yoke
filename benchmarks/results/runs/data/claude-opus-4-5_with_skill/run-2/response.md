This is exactly the failure mode the poka-yoke-data skill describes: "A pipeline that succeeds while producing garbage is the thing to design against."

---

## The retro analysis

**Defect**: Revenue dashboard understated for 3 weeks; discovered at month-close by finance.

**Mistake**: Join returned NULLs after upstream column rename; COALESCE masked them as zeros.

**Hazard** (the system property that made it possible and quiet):
1. No data contract — upstream could rename without breaking anything loudly
2. `COALESCE(x, 0)` on revenue columns — converts missing data into plausible-looking data
3. No reconciliation against a source of truth
4. No assertion that could stop publication

---

## Why your test isn't enough

"Revenue table isn't empty" is **rung 3 (Detection)** and catches only complete failure. Your incident had *rows* — they just said 0 instead of real numbers. That test would have passed every day of those three weeks.

The COALESCE pattern is the core hazard: it's the data equivalent of `except: pass`. It converts "something is broken" into "revenue is low this week," which is a perfectly normal business state nobody investigates.

---

## What the four questions would have caught

| Question | Device | Would it have caught this? |
|----------|--------|---------------------------|
| **Is it there?** (freshness) | max-age assertion | No — data arrived on time |
| **Is there the right amount?** (volume) | Row count ± historical baseline | **Maybe** — if join dropped rows |
| **Is it shaped right?** (schema) | NULL rate check on revenue column | **Yes** — spike in NULLs before COALESCE |
| **Does it agree?** (reconciliation) | Dashboard total = source system total | **Yes** — would have diverged immediately |

---

## The devices to install, ranked by value

1. **Reconciliation (Detection, but the right one)**: Sum revenue in your model daily against a trusted upstream total. This is the only check that catches *logic errors*, not just shape errors. If your join logic is wrong, volume and schema checks pass — the data is well-formed, just wrong.

2. **NULL rate assertion before COALESCE**: Assert that the NULL rate on revenue columns stays below a threshold (probably near zero). Alert on increase. This catches "upstream changed and now we're getting NULLs" directly.

3. **Data contract on the upstream table**: The upstream team declares the schema; renames are breaking changes that fail your pipeline loudly instead of producing NULLs. This is the only Control-level device available here — everything else is Warning/Detection.

4. **Eliminate defensive COALESCE on critical columns**: Replace `COALESCE(revenue, 0)` with a pipeline that *fails* on unexpected NULLs. If missing revenue is a valid business state, model it explicitly (a separate flag); if it's not, don't mask it.

---

## The question to answer

Your "table isn't empty" test is worth keeping as a backstop. But the real decision is: **do you want a reconciliation check that can stop the pipeline, or one that just alerts?**

If finance is the source of truth, can you pull their expected total daily and assert your dashboard matches within a threshold? That device would have caught this on day 1.

`★ Insight ─────────────────────────────────────`
The poka-yoke principle here: COALESCE on revenue is a *hiding device* — it converts a loud failure (NULL in a number) into a quiet one (plausible zero). In data, silence is the defect. The fix isn't better tests; it's removing the thing that made the wrong state look normal.
`─────────────────────────────────────────────────`