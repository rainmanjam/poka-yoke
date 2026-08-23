The pattern here is the same one this repo's own CLAUDE.md calls out: CONTRIBUTING.md, Slack pins, and standup mentions are all **training**, and training degrades. You wrote the rule down in three places and it still didn't stick — that's not a communication failure, it's evidence that the rule has no enforcement mechanism, so it depends on 50 people remembering it every single time they commit.

The fix isn't a fourth reminder. It's a device that makes the violation impossible to merge:

1. **Formatter: don't ask, just fix it.** Add a pre-commit hook (husky+lint-staged, or `pre-commit` framework) that runs the formatter automatically on staged files before commit completes. Nobody has to remember to run it — it just runs. If someone bypasses with `--no-verify`, that's rare and visible, not the default failure mode.

2. **CI gate as the actual backstop.** Pre-commit hooks are opt-in in practice (people can skip install, skip the hook). The thing that can't be skipped is a required CI check on the PR — `git diff --check` against formatter output, or just re-running the formatter in check mode and failing the build if it changes anything. Make it a required status check in branch protection so the PR literally cannot merge red.

3. **Type annotations: turn it into a lint rule, not a convention.** "Add type annotations to new code" is currently a matter of taste/memory. Make it mechanical: `mypy --strict` (Python) or `noImplicitAny` + a `no-explicit-any`-style ESLint rule (TS) scoped to changed files, failing CI. If your type checker can't cheaply enforce "new code only," gate it on a ratchet — track the count of `Any`/untyped defs and fail if it goes up.

4. **Retire the human-readable version once the device exists.** Once CI enforces it, delete the CONTRIBUTING.md prose telling people to do it manually — a rule that's both documented and enforced invites the enforcement to be seen as optional guidance rather than the actual gate.

Net effect: authors get fast local feedback (pre-commit), and even if they ignore that, the PR literally cannot land unformatted or untyped. Nobody has to remember anything for the rule to hold.

If you want, I can help write the actual pre-commit config and CI check for whatever formatter/type-checker stack this repo uses — what language/tooling are we talking about?