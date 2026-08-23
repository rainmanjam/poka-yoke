Using the poka-yoke **guardrails** skill (routed there by the router: "we agreed to X and people still do not"). Here's the answer it gives, and it starts with a reframe.

**Stop adding reminders — you've maxed out that channel.** CONTRIBUTING.md, the Slack pin, and two standup mentions are all the same device: training. In Shingo's terms that's rung 0 — it relies on people remembering, and remembering degrades under deadline pressure. A 50% compliance rate after three reminders isn't a discipline problem; it's the expected decay curve of any rule that lives in prose. The fix is to move the rule out of people's heads and into the pipeline, where it applies itself.

Concretely, in order of value:

1. **Make formatting automatic, not checked.** The highest-rung device for a formatter isn't a gate at all — it's removing the human step. Commit editor config to the repo (`.vscode/settings.json` with format-on-save, or the equivalent) and add a pre-commit hook that *runs the formatter and fixes the files* rather than rejecting the commit. Nobody has to remember anything; the mistake becomes unmakeable.

2. **CI required checks as the authority.** Pre-commit hooks are bypassable (`--no-verify` exists, and people under deadline use it), so back both rules with CI jobs: a format check (`prettier --check` / `ruff format --check`) and the type checker (`tsc --noEmit`, `mypy`, whatever fits your stack). Run the same script in hook and CI so they can't drift.

3. **Branch protection, marking those checks Required.** This is the piece that turns everything above from advisory into enforcement. Without it, a red CI check is just another reminder people can merge past. This is the one step that needs an admin click (or `gh api`), and it's the actual answer to your question: right now an unformatted PR *can* merge, so sometimes it does.

4. **Baseline, then ratchet — or the gate gets reverted by Friday.** Don't turn on strict typing repo-wide; it'll fail on hundreds of pre-existing lines and teach everyone that the gate is noise. Enforce on **changed files only** (or generate a baseline and fail only new violations). The count can only go down, and nobody is blocked by code they didn't write. Also keep the hook fast (<~5s) and make the failure message state the exact fix command — a gate that says "run `npx prettier --write .`" gets complied with; one that says "check failed" gets worked around.

5. **Prove each gate fires once.** Push a deliberately unformatted commit, watch CI go red, fix it, watch it go green. An enforcement rule nobody has ever seen fail is a rumor, not a device.

`★ Insight ─────────────────────────────────────`
The two rules differ in achievable rung: formatting can reach **control** (auto-fix — the mistake can't exist), but "add type annotations to new code" can only reach **warning** (a CI gate at merge time), because no tool can force annotations at typing time. That's why #4 matters more for typing — a warning-rung device survives only if it never cries wolf on old code.
`─────────────────────────────────────────────────`

If you tell me your stack (language, CI provider), I can write the actual configs — hook, workflow, and the ratchet setup — ready to open as a PR.