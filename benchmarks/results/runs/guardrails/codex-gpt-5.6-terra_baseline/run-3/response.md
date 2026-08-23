Stop adding reminders—the team has already received the instruction. Make the repository enforce it.

- Run the formatter and type checker in CI; block merges when either fails.
- Add a pre-commit hook or commit-time check that auto-formats changed files, so the easy path is compliant by default.
- Make type checking fail on newly introduced untyped public code (or enforce a ratcheting baseline), rather than demanding an immediate whole-codebase cleanup.
- Put the same commands behind one developer command, e.g. `make check` / `just check`, and have CI invoke that exact command.
- Prove each guard works: intentionally submit an unformatted change and an untyped new function; verify both checks go red, then restore them.

The contributing guide, Slack pin, and standup mentions are training. A merge gate and automatic formatter are the device.