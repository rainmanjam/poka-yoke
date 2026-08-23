Text and reminders can't fix this — they're the same category of "training" your own CLAUDE.md warns against; the fact that people already saw CONTRIBUTING.md, Slack, and standup twice and still didn't comply is the proof it's not a communication problem. The fix is to make the two behaviors either automatic or blocking, so compliance doesn't depend on anyone remembering:

**1. Auto-format on commit, don't ask for compliance**
Add a pre-commit hook (husky+lint-staged, pre-commit framework, or a native git hook) that runs the formatter on staged files and either auto-fixes and re-stages, or blocks the commit if it can't. Nobody has to *remember* to run the formatter — the tool runs it for them. This alone should kill most of the "unformatted" half.

**2. Make CI fail on violations, not just report them**
If CI currently runs the formatter/type-checker in "check" mode but doesn't block merge, that's your leak. A red CI check that's advisory gets ignored under deadline pressure. Make format-check and type-check required status checks so the PR literally cannot merge until they pass.

**3. Baseline the existing code so the gate doesn't punish unrelated work**
If you gate the whole repo immediately, people editing old, unformatted/untyped files get blocked by pre-existing violations that aren't theirs — that breeds resentment and workarounds (`--no-verify`). Instead, gate only *changed lines/files* (most formatters and type checkers support this — e.g., `git diff --name-only` piped into the tool, or a baseline/ignore file that's frozen at today's state and only shrinks).

**4. Ship the editor config, don't rely on individual setup**
Commit `.editorconfig`, format-on-save settings for the team's editor(s), and pin the formatter version in the repo (package.json/pyproject.toml) so "it formatted differently on my machine" isn't an excuse.

**5. If you want a softer ramp, warn locally before you block centrally**
A pre-push hook that runs the same checks CI will run, with a fast local fail, gets people the feedback before they even open the PR — cheaper for everyone than a red CI check 10 minutes later.

The sequencing that tends to land well without a revolt: ship the pre-commit auto-formatter first (invisible, no one can violate it), then flip CI to required/blocking a week later once most new commits are already compliant, with the changed-files-only baseline so it's not punishing old code.

What's your stack (language/formatter/type-checker), and do you have CI already running these checks in non-blocking mode, or not at all yet? That determines whether step 1 or step 2 is the faster win.