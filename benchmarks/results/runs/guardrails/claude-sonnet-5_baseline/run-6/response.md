Documentation, Slack pins, and standup mentions are all the same category of fix: they rely on people remembering. Two weeks of decay is the expected outcome, not a fluke.

The fix that actually works is to stop asking people to remember and make the rule structurally unavoidable:

1. **Pre-commit hook that runs the formatter, not documents it.** `pre-commit` / `husky` + `lint-staged` auto-formats staged files before the commit completes. Nobody has to remember — there's no unformatted commit to make.
2. **CI gate that fails on drift.** A check that runs the formatter and diffs the result (`prettier --check`, `black --check`, `gofmt -l`) and blocks merge on nonzero exit. Same for types — compile with `strict`/`noImplicitAny` (or your language's equivalent) so untyped new code fails the build rather than passing review by omission.
3. **Prove the gate isn't a rumor.** Per this repo's own rule (`CLAUDE.md`): before trusting it, break the thing on purpose — commit unformatted code, commit an untyped function — and confirm the check actually goes red. A formatter check that silently passes on bad input is worse than no check, because it looks like coverage.
4. **Scope type-checking to new/changed lines only** if the existing codebase isn't fully typed yet, so the gate doesn't block unrelated work with a wall of preexisting errors.

Net effect: the policy moves from "everyone remembers to do X" to "X is either already done for you or the PR can't merge." That's the difference between training and a device.

Want me to wire up the pre-commit hook and CI check for this repo specifically? I'd need to know what formatter/type checker you're standardizing on.