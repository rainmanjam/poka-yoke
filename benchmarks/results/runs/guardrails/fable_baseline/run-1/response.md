Short answer: stop trying to get people to follow it. You've already done everything training can do — CONTRIBUTING.md, a pin, two standups — and got ~50%. That's not a compliance problem, it's the expected decay curve of an instruction. The fix is to make unformatted/untyped code unable to reach `main`, so nobody has to remember anything.

**Separate the three things**

- *Defect*: unformatted/untyped PRs land.
- *Mistake*: someone commits without running the formatter.
- *Hazard*: **the repo accepts a commit that was never formatted, and a PR that was never typechecked can be merged.** That's the property to remove. "People forget" is not a terminal answer — forgetting is only possible because the system doesn't check.

**The ladder, for this case**

| Rung | Device |
|---|---|
| **Control** | CI job runs `<formatter> --check` and the type checker on every PR; the job is a **required status check** in branch protection, so the merge button is disabled until it passes. This is the one that actually ends the problem. |
| **Control (local)** | Pre-commit hook (`pre-commit`/husky/lefthook) that formats on commit. Good for speed, but it's opt-in per clone, so it's a convenience layer, not the gate. |
| **Warning** | A bot that auto-formats the branch and pushes a fixup commit — removes the friction instead of the person. |
| **None** | Another reminder, a PR template checkbox, a "required reviewer." That's what you've been doing. |

**Two things that matter when you build it**

1. **Annotations need a real definition.** "Add type annotations to new code" is unenforceable as stated. Pick the concrete rule the checker can evaluate — e.g. mypy `disallow_untyped_defs` / `--strict`, or `noImplicitAny` — and scope it to new files or use a ratchet (baseline the current count of untyped defs, fail if it goes up). Otherwise the check either blocks on legacy code or checks nothing.
2. **Prove it fails before you trust it.** Open a PR with a deliberately unformatted, untyped function and watch the merge button go grey. A check that has never gone red is a rumour. (The `validate.yml` in this repo exists for exactly this reason.)

**Why this works where standups didn't**

Nobody has to agree, remember, or care. The half who comply already do; the other half get a red X and a one-line fix command, and it costs them a minute instead of costing a reviewer a nag. And the rule stops depending on you being the person who keeps pinning it.

If you want, tell me the language/toolchain and I'll write the workflow + branch-protection steps, including the ratchet for existing untyped code.