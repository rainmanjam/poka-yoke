Using poka-yoke's guardrails mode. Short version: you've now tried the same device four times, and it's the one device that doesn't work.

CONTRIBUTING.md, the pin, and both standups are the same instrument — **training**. Training degrades; that's not a fact about your team, it's the reason poka-yoke exists. A fifth reminder gets you a fifth data point. The 50% figure isn't a discipline problem, it's a measurement of how much a written rule holds after two weeks, and 50% is roughly what it always is.

So the question to ask isn't "how do I get people to remember" — it's "what would make forgetting impossible."

## The two rules need different devices

They look alike but sit at different rungs.

**Formatting is fully controllable.** Nobody actually wants to decide formatting, so delete the decision:

- Commit editor config (`.editorconfig` + a checked-in `.vscode/settings.json` with format-on-save) so the common case never arises.
- A pre-commit hook that **rewrites** the file rather than yelling about it. Auto-fix, not a failure — the mistake becomes unmakeable rather than punished.
- The same formatter in `--check` mode as a **required** CI check. This is the load-bearing part: the hook is for speed, CI is for authority, because `--no-verify` exists and people under deadline use it.

Net: unformatted code can't reach main. Rung 1.

**Types can't go to rung 1 today.** Turning on `mypy --strict` / `noImplicitAny` repo-wide gives you hundreds of errors on code nobody is touching, and the check gets reverted by Friday — which is worse than nothing, because it teaches the team that gates are negotiable. Instead **ratchet**: run the type check on changed files only, or generate a baseline of current violations and fail only on new ones. The count can only go down. Required check on new code = rung 1 at the merge boundary, rung 2 while authoring.

## Two things that make it land instead of grate

**Run it report-only for a week first.** You get the real number (better than "about half"), the baseline file, and — importantly — the rollout reads as instrumentation rather than a crackdown on the people who've been non-compliant.

**Write the failure message to teach.** `error: format check failed` produces a confused engineer and a workaround. `Run 'make fmt' and commit — this is auto-fixable` produces a fixed PR. That's the one place prose belongs in a device: at the moment of failure, where it's guaranteed to be read.

None of this holds without **branch protection with required checks**. That's the actual enforcement; everything above is just fast feedback.

---

Tell me the stack (Python — ruff/black/mypy? TypeScript — prettier/tsc?) and I'll write the pre-commit config, the CI workflow, and the ratchet script, then deliberately break each one so you can watch it go red before you ask anyone to live under it. I'd also drop the CONTRIBUTING.md paragraph to one line pointing at the tooling — once the device exists, the prose is just something else to fall out of date.