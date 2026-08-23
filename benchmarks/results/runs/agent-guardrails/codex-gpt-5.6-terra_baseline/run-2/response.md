Nothing wrong with the wording. You’re asking a probabilistic system to remember a prohibition; repeating it in caps only marginally changes the odds.

Turn both rules into devices:

- **Generated files:** make edits fail locally and in CI. For example, reject staged changes under `src/generated/` with a pre-commit hook, and have CI compare regenerated output or fail if that path appears in the diff. If regeneration is legitimate, expose one explicit script/workflow that performs it.

- **Force push:** remove the capability where possible. Protect the remote branch so force pushes are rejected, disallow history rewrites in branch rules, and use a wrapper/alias or hook that refuses `git push --force` / `--force-with-lease`. CI cannot reliably prevent a push that already happened; the server must enforce this.

Keep `CLAUDE.md` concise as explanation and routing (“generated code is produced by `…`; run that command”), but don’t treat it as the control. The useful design question is: *what command should be unable to succeed when this rule is violated?*