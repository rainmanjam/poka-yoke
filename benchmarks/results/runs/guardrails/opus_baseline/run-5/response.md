You've done four rounds of training. Training degrades — that's the whole finding here, and two weeks of ~50% compliance is the measurement proving it. A fifth round (nagging in review, a PR checklist) will land at the same place.

The fix is to stop asking people to remember and make the unformatted/untyped PR unable to merge.

**The device, cheapest to most authoritative:**

1. **Formatter — don't check it, apply it.** Formatting is not a judgment call, so nobody should be spending attention on it. A pre-commit hook that *rewrites* the file (Black/Ruff-format, Prettier) means the mistake becomes impossible rather than caught. Rung 1 (control).
2. **Same command as a required CI check.** `--no-verify` exists and people under deadline use it, so the hook is for speed and CI is for authority. Run the identical script in both so they can't drift. With branch protection on, this is what actually ends the conversation.
3. **Type annotations — ratchet, don't flip.** `mypy --strict` on a repo that's never had it produces hundreds of errors, and the rule gets reverted by Friday. Enforce on **changed files only**, or generate a baseline and fail only on *new* violations. The count can only go down.
4. **Make the failure message teach.** `run 'make fmt' and commit` beats `error: E501`. This is the one place prose belongs in a device — at the moment of failure, when someone is guaranteed to read it.

Then delete the CONTRIBUTING.md paragraph, or rewrite it as "CI enforces this; here's how to run it locally." Leaving the rule in prose *and* in the gate teaches people the prose is where rules live.

`★ Insight ─────────────────────────────────────`
- The two rules aren't the same hazard. Formatting is fully mechanical → auto-fix it (control). Typing requires human judgment → gate it (warning). Applying one strategy to both is why these agreements usually fail halfway.
- Half-compliance is the diagnostic signal: the rule is clear and people agree with it. That rules out "they don't understand" and leaves "nothing stops them," which is a device problem.
- Verify the gate fires before trusting it — push a deliberately unformatted branch and watch it go red. A check that has never gone red is a rumour, not a device.
`─────────────────────────────────────────────────`

**One decision that's yours, not mine:** the ratchet policy for types. Three options, real tradeoffs — (a) changed-files-only: zero backlog work, but a file touched once must be fully typed, which can turn a one-line fix into an afternoon; (b) baseline file of existing violations: no surprise blast radius, but the baseline rots and needs pruning; (c) per-directory opt-in as modules get cleaned: slowest, most predictable. Which fits your team's tolerance for a bad week?

Tell me that plus your language/toolchain and I'll write the pre-commit config, the CI workflow, and the `gh api` command for branch protection — and demonstrate each one failing before it passes. This repo has `CONTRIBUTING.md` and `.github/workflows/validate.yml` but no `.pre-commit-config.yaml`, so if it's this repo, that's the gap.