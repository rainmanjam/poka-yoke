Two weeks of Slack pins and standup mentions not landing is exactly the pattern this repo's own CLAUDE.md calls out: **"If your change relies on someone remembering something, it is not finished."** CONTRIBUTING.md is training, and training degrades — you need a device that makes unformatted/untyped code impossible to merge, not something people have to remember to do.

The fix is a CI gate + pre-commit hook, not more documentation:
- **CI check that fails the PR** if `<formatter> --check` or the type checker reports errors — this is the one that actually matters, since it can't be skipped
- **Pre-commit hook** (via husky/lefthook/pre-commit) that runs the same check locally, so people get the failure before pushing instead of after
- **A baseline/ratchet** for existing untyped code so the gate only blocks *new* violations, not the whole legacy tree at once — otherwise it's too painful to turn on and someone disables it

What's your stack (language/formatter/CI provider)? I can write the actual gate and hook config rather than another policy doc — happy to also show it failing on an unformatted commit first, then passing, so you have proof it actually blocks before you roll it out.