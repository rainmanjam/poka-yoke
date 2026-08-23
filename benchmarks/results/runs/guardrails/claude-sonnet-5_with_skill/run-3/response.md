The core issue: everything you tried — CONTRIBUTING.md, Slack, standup — is the same device repeated three times. All three rely on someone remembering. That's rung 0 on the poka-yoke scale (training), and training decays; two weeks is roughly the half-life you're seeing. No amount of restating a rung-0 rule turns it into enforcement.

The fix is to move the rule from "documented" to "mechanically gated" — pick the earliest gate in the lifecycle that can hold it, and back it with one that can't be skipped:

| Gate | Speed | Bypassable? |
|---|---|---|
| Editor + lint (format-on-save, type-check in IDE) | seconds | yes, ignored |
| Pre-commit hook (formatter + basic type check) | seconds | yes (`--no-verify`) |
| **CI required check** | minutes | **no**, if branch protection is on |

Concretely:
1. **Pre-commit hook** running the formatter and a fast type check on changed files — catches most cases before they even reach a PR, costs nothing to remember.
2. **CI required check** running the same formatter (`--check` mode, not "fix and pass") and full type check — this is the one that actually can't be bypassed, but only if it's wired into **branch protection** as a required status check. A CI job that merely runs and reports isn't enforcement; a red X that blocks merge is.
3. **Baseline first, then ratchet.** If you turn strict type-checking on across the whole repo today, you'll get a wall of pre-existing failures and the check will get disabled by Friday. Instead: enforce formatting/types on changed files only, or snapshot current violations as a baseline and fail CI only on *new* ones. The count can only go down from there — this is what makes strictness stick instead of getting reverted.
4. **Make the CI failure teach**, not just fail — the message should say exactly what command to run (`npm run format`, `mypy path/to/file.py`) so a blocked PR is self-service, not a Slack question back to you.

Two of the three prose-based things you did (CONTRIBUTING.md, standup mentions) can stay as *context* for why the rule exists — that's fine, it's just not the enforcement mechanism.

What's your stack (language, CI provider — GitHub Actions, etc.)? I can write the actual pre-commit config and CI workflow, including the baseline step so it doesn't block the ~50% of in-flight PRs on day one.