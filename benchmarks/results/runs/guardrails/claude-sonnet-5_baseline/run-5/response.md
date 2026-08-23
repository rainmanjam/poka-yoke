The pattern here is exactly what this repo's CLAUDE.md calls out: CONTRIBUTING.md, Slack pins, and standup mentions are all **training** — they rely on people remembering. Training decays; that's not a discipline problem, it's a design problem with the enforcement mechanism.

The fix is to make "unformatted or untyped" impossible to merge, not more-often-mentioned:

1. **Pre-commit hook** — run the formatter and a type-check in `pre-commit` (or husky/lefthook for JS) so it either auto-fixes on commit or blocks it. This catches it before it ever becomes a PR.
2. **CI gate on the PR** — a required check that runs formatter `--check` and the type checker, and fails the build if either doesn't pass. Branch protection makes this un-skippable, even by accident.
3. **Auto-fix instead of block where you can** — if the formatter is idempotent, have CI (or a bot) push the formatted diff rather than just rejecting the PR. Removes the friction that causes people to route around the check.

Once that's in place, delete the CONTRIBUTING.md prose about running the formatter — a rule enforced by CI doesn't need to also live in a doc, and a stale doc that says "please do X" next to a CI job that already forces X just invites drift between the two.

If you want, I can look at what's already in `.github/workflows/` here and draft the actual hook/CI config — want me to do that?