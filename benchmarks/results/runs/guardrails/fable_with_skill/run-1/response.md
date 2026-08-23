★ Insight ─────────────────────────────────────
Your three interventions — CONTRIBUTING.md, a Slack pin, standup reminders — are all the same intervention: training. In Shingo's terms they're rung 0 on the regulatory ladder, and the ~50% compliance at two weeks isn't a people problem, it's training decaying exactly on schedule. The fix isn't a fourth reminder; it's moving the rule out of memory and into a machine.
─────────────────────────────────────────────────

**Stop trying to get people to follow it. Make the PRs unable to merge without it.** A rule that lives in prose has a half-life of about one onboarding; the same rule wired into CI applies itself and costs nothing to remember. Concretely, in order of value:

1. **Make formatting a non-task, not a rule.** Nobody should "remember to run the formatter." Commit editor config to the repo (format-on-save in `.vscode/settings.json` / `.editorconfig`), add a pre-commit hook that *auto-fixes* rather than complains, and add a CI job that runs `formatter --check`. Formatting is the one rule that can reach **Control** almost for free.

2. **Type annotations become a required CI check** — `mypy --strict`, `tsc --noEmit`, whatever fits your stack — but **ratcheted**: enforce on changed files only, or generate a baseline of existing violations and fail only on new ones. This matters enormously in your situation: half your codebase is presumably untyped, and a gate that fires on code people didn't write teaches the whole team to bypass gates, which is worse than no gate.

3. **Branch protection with both as required checks.** This is the piece that makes everything else enforcement instead of suggestion. A pre-commit hook alone is not enough — `--no-verify` exists and people under deadline use it. Hook for speed, CI for authority, same script in both so they can't drift.

4. **Make the failure message teach.** Not `error: check failed` but "this file isn't formatted; run `make fmt` and re-push." The moment of failure is the one place someone is guaranteed to read the instruction — that's where the prose from CONTRIBUTING.md actually belongs.

5. **Verify the gate fires before you announce it.** Open a deliberately unformatted PR, watch it go red, fix it, watch it go green. A gate that has never been seen failing is a belief, not a device.

One reframe for the next retro: the agreement itself was fine — what was missing was the follow-up question "what *device* enforces this?" A useful team norm going forward is that a process agreement isn't closed until the enforcing check is merged.

Two ready-made starting points sit in this repo: `plugins/poka-yoke/assets/devices/pre-commit/` and `assets/devices/github-actions/` (formatter, type check, required-check workflow templates). If you tell me the team's language and CI (e.g. Python + GitHub Actions), I'll write the actual configs — the pre-commit config, the ratcheted type-check job, and the exact branch-protection settings to click.