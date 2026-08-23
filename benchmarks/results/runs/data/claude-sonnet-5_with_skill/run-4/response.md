No — that test would not have caught this incident. Walk through why, then what would.

**Why "not empty" doesn't cover this failure**

The table had rows the whole three weeks. The join returned nulls, and `COALESCE(..., 0)` turned those nulls into valid-looking zero rows. Row count stayed normal, schema stayed valid, nothing was empty. A not-empty check passes on both the working pipeline and the broken one — which is exactly the "check that cannot fail" failure mode: it's not a device, it's a rumor of one. Before trusting it for anything else, prove it can go red: temporarily reintroduce a null-producing join and confirm the test doesn't flag it either (it won't).

**What actually breaks in this incident**

Two independent mistakes, and each wants its own device:

1. *The join silently produced nulls when the upstream column renamed.* Renames should be treated as drop-plus-add, not absorbed silently.
2. *The nulls were coalesced to 0 instead of surfaced.* This is the data-world equivalent of `except: pass` — it converts a loud failure into a quiet, plausible-looking one.

**Devices, ranked**

- **Null-rate assertion on the pre-coalesce join output** (Warning, contact lens — "is it shaped right"). Assert the join match rate before you ever coalesce, e.g. fail if >X% of rows are unmatched. This is what should have fired the day the rename landed, not three weeks later at close.
- **Reconciliation against the source system** (Warning/Detection, and per the skill the one that matters most for revenue specifically — it's the only check that catches a logic error where the output still *looks* well-shaped). Sum of revenue in the warehouse vs. the upstream system's total, with a tolerance. A join fanning nulls into zeros moves the total; reconciliation is the thing that notices.
- **A schema contract on the upstream table** (closer to Control, contact lens). The producer declares column names/types; your ingest validates against it and quarantines on mismatch instead of letting a rename flow silently into a join miss. This is what stops the *next* rename from being a surprise at all, rather than catching its symptom downstream.
- **Kill the silent coalesce.** If a revenue join can legitimately have no match, that needs an explicit, named case (e.g. `unattributed_revenue`), not a default that's indistinguishable from "correctly zero."

Row-count/not-empty is still worth keeping as a floor-and-ceiling volume check against the same weekday historically — it catches a different failure mode (partial load) — just don't let it stand in for the null-rate and reconciliation checks, which are what this incident actually needed.

One thing that's a genuine judgment call rather than mine to make: the tolerance on the reconciliation check (exact match vs. some % drift threshold) depends on how your revenue pipeline handles timing/currency rounding — want to sketch that threshold logic, or should I draft a starting point for you to tune?