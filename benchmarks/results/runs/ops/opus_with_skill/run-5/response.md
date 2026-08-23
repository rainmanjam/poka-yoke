Using the poka-yoke router → **`ops`** mode (schema migration + deploy timing). There's no real PR in this repo — `legacy_email` only appears in `benchmarks/results/runs/ops/`, so I'm answering from your description, not from code I inspected.

Short answer: **ship half of it this afternoon, not the drop.**

## The four things you need before shipping

**1. What's irreversible, and what restores it?** The `DROP COLUMN` is. The code change isn't — that reverts in minutes. Once the column is dropped, `git revert` does not bring the data back; only a restore from backup does, and that means point-in-time recovery of the whole database plus re-applying everything written since. If nobody has *actually performed* a restore recently, treat that data as unbacked when you size the risk.

**2. What breaks during the rollout window?** This is the part that makes it not a small change. Deploys aren't atomic. If the migration and the code land together, there's a window where old instances — still selecting `legacy_email` — run against a schema where it no longer exists. That's `UndefinedColumn` errors on every request through those three paths until the rollout finishes. The outage isn't the drop; it's the window.

**3. Can the irreversible part ship separately?** Yes, and this is the whole recommendation. Split it:

- **Today:** deploy only the code that stops reading `legacy_email`. Fully reversible, safe on a Friday, no schema change.
- **Next week:** the `DROP`, as its own deploy, once the code has baked and you've confirmed zero reads.

That's the contract step of expand/contract. Steps that keep the old column readable are all revert-able; only the drop isn't, which is exactly why it earns its own deploy.

**4. If it goes wrong, who's around and how fast is rollback?** Code-only: two-minute revert, fine with a skeleton crew. Column-dropped: multi-hour restore, and on a Friday evening you're paging people who are already offline. Timing isn't superstition — it's staffing math.

## Before the drop, next week

"Three places in the code" is a grep of *one repo*. Check the readers that grep can't see: ETL jobs and warehouse syncs, BI dashboards, analytics SQL, other services, saved exports, ad-hoc notebooks. A column named `legacy_email` is exactly the kind of thing something dusty still selects.

## Devices worth installing

- **CI gate (Control):** block any changed migration containing `DROP`/`TRUNCATE`/`ALTER … DROP` unless the PR carries an explicit approval label. Prevents co-deploying a destructive migration with dependent code — permanently, not just this once. See the `guardrails` mode for the gate.
- **Snapshot immediately before the drop (Reversibility):** and verify it restores, rather than trusting that it would.

Want me to write the CI gate? It's the device that makes this a one-time conversation.