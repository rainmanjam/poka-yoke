Using `poka-yoke:retro` — this is exactly the failure the framework is about.

## Separate the three things

- **Defect:** ~half of PRs arrive unformatted/untyped.
- **Mistake:** someone commits without running the formatter.
- **Hazard:** *the repo accepts unformatted, untyped commits.* Nothing in the system can tell the difference between a compliant PR and a non-compliant one.

CONTRIBUTING.md, the Slack pin, and two standups are all the same rung: **training**. Training degrades, fastest for the people with the most context-switching. 50% after two weeks is a normal decay curve, not a discipline problem — saying it a third time buys you the same number. The question isn't "how do I get people to remember," it's **"why does a human decide whether the formatter runs?"**

## Formatting — eliminate the rule, don't enforce it

Formatting is machine work. Delete the rule rather than police it.

1. Commit the formatter config **and a pinned version** to the repo, so "mine formatted it differently" stops being real.
2. CI runs `<formatter> --check`, and you mark it a **required status check** in branch protection. That's the Control rung: an unformatted PR is *unmergeable*, not frowned upon.
3. Stronger still: have CI format and push the fixup commit itself. Then non-compliance isn't expressible.
4. Commit `.editorconfig` + editor format-on-save settings so it usually happens before the commit even exists.

A pre-commit hook is Warning rung — `--no-verify` skips it, and installing it depends on the same memory that just failed. Keep it as a fast local echo of CI, never as the thing you rely on.

## Types — ratchet, don't decree

Types can't be auto-fixed, so gate them scoped to *new* code:

- Typechecker in CI with a **baseline of existing errors that is only allowed to shrink**. New untyped code fails; nobody has to boil the legacy ocean.
- Same treatment: required status check.

## What should have caught this and didn't

Code review. Reviewers approved half of these PRs. Humans are bad at diffing whitespace and are right not to spend attention there. That's also the argument to make to the team — this isn't a compliance crackdown, it's giving review its attention back.

## Accepted risk

Admins can bypass branch protection, and CI config is editable in a PR. Both are logged and visible — unlike forgetting, which leaves no trace.

`★ Insight ─────────────────────────────────────`
The tell that a fix is rung zero: it works only if a person recalls it at the right moment. Docs, pins, standups, checklist items, and "add a required reviewer" all share that property — which is why they fail identically.
`─────────────────────────────────────────────────`

What language and CI are you on? I'll write the workflow and the type ratchet config concretely — the baseline-only-shrinks piece is where most teams get it wrong and end up with a check that can't go red.