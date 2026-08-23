Using poka-yoke (retro + guardrails) — here's the diagnosis and the fix.

**Why it's not working:** everything you did — CONTRIBUTING.md, the Slack pin, standup mentions — is rung 0 on the poka-yoke ladder: it relies on someone remembering. That's not a criticism of your team; it's a property of any rule that only lives in prose. A wiki rule has a half-life of about one onboarding cycle. No amount of repetition turns a memory-dependent rule into an enforced one.

**The hazard, stated properly:** there is no gate between "code that violates the agreement" and "code that merges." The agreement is real, but nothing in the pipeline checks it.

**What actually closes this — pick the earliest gate that can't be skipped:**

| Gate | Catches it | Bypassable |
|---|---|---|
| Editor/format-on-save | instantly, for people who have it configured | yes, silently |
| Pre-commit hook (formatter + type check) | at commit time | yes (`--no-verify`) |
| **CI required check + branch protection** | before merge | **no** — this is the one that matters |

Do both, but don't stop at pre-commit — `--no-verify` exists and people under deadline use it. The pre-commit hook is for fast feedback; the CI check with branch protection is the actual enforcement, because it can't be skipped.

Two more things that make this land instead of getting reverted by Friday:
- **Baseline first.** If you turn strict type-checking on for the whole repo today, you'll get a wall of pre-existing failures and someone will revert the rule. Enforce formatting/types on changed files only (or fail only on new violations), so the count only goes down.
- **Make the failure message teach.** `error: unformatted` breeds a confused dev and a workaround. `error: run \`npm run format\` — 3 files unformatted` gets fixed in ten seconds.

Want me to set up the actual `.pre-commit-config.yaml` and the CI required-check workflow for this repo's stack? I'd baseline against current violations so it doesn't block in-flight PRs, and show you the config before writing anything.