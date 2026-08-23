You’ve already done the training part. The next move is to replace memory with a gate.

Make “formatted and typed” mechanically required:

- Add CI checks that fail a PR if formatting or type checks fail.
- Provide a one-command local check (for example, `make check` or `npm run check`) that runs the formatter and type checker.
- Add a pre-commit hook that formats automatically; make CI the backstop, since hooks can be bypassed.
- Configure editor settings so save formats files and surfaces type errors immediately.
- Scope type enforcement to new/changed code at first, so existing debt doesn’t block unrelated work.
- Make the PR template/checks automatic—don’t rely on an author attestation.

Most importantly, prove the checks work: intentionally submit an unformatted, untyped change and confirm CI rejects it; then fix it and confirm it passes. A passing check that scans nothing is just another reminder in disguise.