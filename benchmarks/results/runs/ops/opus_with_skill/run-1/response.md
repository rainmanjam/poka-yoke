Read: router → `ops` (deploy/migration), plus `audit` finding structure and `guardrails` for the gate.

## Short answer

Friday isn't the problem. **The co-deploy is.** Ship the code today, drop the column next week — that splits a change that can't be rolled back into two that can.

## The four questions

**1. What's irreversible, and what restores it?**
`DROP COLUMN legacy_email` is irreversible. Nothing in your deploy pipeline restores it. The real path is a point-in-time restore to a side instance, extract the column, backfill — hours, and only if someone has actually *performed* a restore recently. If nobody has, treat that data as unbacked when you size the blast radius.

**2. What breaks during the rollout window?**
This is the part CI cannot see. Deploys aren't atomic. For however long your rollout takes, **old pods still reading `legacy_email` are hitting a schema where it no longer exists.** Every request through those three code paths errors. Green CI proves new code works against new schema; it never runs old code against new schema, which is the only state your users will actually experience.

**3. Can the irreversible part ship separately?**
Yes, and it's the whole recommendation. You're doing expand/contract with the contract fused to the read-switch:

- **Today:** deploy the code that stops reading `legacy_email`. Fully reversible — the column is still there, so a revert just works.
- **Next week, after it's baked:** deploy the `DROP` alone, with zero code changes in it.

**4. If it goes wrong, who's around and how fast is rollback?**
Right now: **rollback is broken.** Revert the code and the reverted version reads a column that no longer exists — so your escape hatch is also an outage. A change that reverts in two minutes is genuinely fine on a Friday afternoon. This one currently has no revert, and that's what makes the timing question real.

`★ Insight ─────────────────────────────────────`
"CI is green" and "this deploy is safe" measure different things. CI tests one consistent (code, schema) pair. A deploy passes through a *mixed* state that no test in your suite constructs — old code, new schema. That window is where co-deployed migrations fail, which is why the fix is sequencing, not more tests.
`─────────────────────────────────────────────────`

## One thing to check before even the code deploy

"Three places in the code" is three places *in this repo*. Grep won't see: dbt models and warehouse views, BI/Metabase saved queries, ETL exports, admin or ops scripts, another service on the same database, read replicas. Check those before the drop, not before the merge.

## The device

Everything above is reasoning someone has to remember next time. The device that doesn't degrade — from `assets/devices/github-actions/poka-yoke-gates.yml`, the `migration-safety` job:

```yaml
if: "!contains(github.event.pull_request.labels.*.name, 'destructive-migration-approved')"
# blocks +DROP TABLE|COLUMN, TRUNCATE, ALTER ... DROP in changed migrations
```

**Rung: Control** for the accident — a destructive migration cannot merge unless someone applies the label, which turns a slip into an on-the-record decision. Not Control against intent (the label is one click), so pair it with branch protection making the check required. Prove it fires before you trust it: push a PR with a `DROP`, watch it go red, add the label, watch it pass.

Want me to write that gate into the repo you're deploying from?