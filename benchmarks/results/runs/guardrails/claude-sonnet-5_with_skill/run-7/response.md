Used the poka-yoke guardrails skill for this — the situation it's built for.

**Diagnosis:** CONTRIBUTING.md, a pinned Slack message, and two standup mentions are all the same rung: rung 0, training. They rely on someone remembering, and training decays — that's not a discipline problem on your team, it's the predictable outcome of not having a device. Two weeks in, you're seeing exactly the failure rate rung-0 fixes always produce.

**What would actually hold:**

1. **Make it a required CI check, not a request.** Run the formatter's `--check` mode and the type checker (`tsc --noEmit`, `mypy`, whatever your stack uses) as a required status check, wired into branch protection so the PR literally cannot merge red. This is Control rung — the only fix on your list so far that doesn't depend on anyone remembering.
2. **Back it with a pre-commit hook for speed**, not as the enforcement itself — `--no-verify` exists and people under deadline use it. The hook is for fast feedback; CI is the authority. Run the same script in both so they can't drift apart.
3. **Baseline first, ratchet second.** If you turn strict formatting/typing on for the whole repo today, you'll get hundreds of failures on old code and the check gets reverted by Friday. Instead, gate only on changed files (or generate a baseline of existing violations and fail only on *new* ones). Violation count can only go down from there — that's how the rule actually lands instead of getting rage-quit.
4. **Make the failure message teach.** `error: 3 files not formatted` produces a confused dev and a workaround. `error: 3 files not formatted — run \`black .\` and recommit` produces a fix. This is the one place prose still belongs, because it fires exactly when someone's reading.

The editor autoformat-on-save + type hints in the IDE are worth turning on too — earliest possible feedback — but they're bypassable, so the CI gate is what actually matters.

Want me to write the actual pre-commit config and CI workflow? Tell me the language/formatter/type-checker you're using and I'll draft both, plus verify them by deliberately committing unformatted/untyped code and showing the gate reject it before you roll it out.