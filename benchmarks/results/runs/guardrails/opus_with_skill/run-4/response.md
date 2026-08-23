Using **poka-yoke → guardrails** — you have a rule that needs enforcing, not documenting.

## The diagnosis

You've now deployed the same device three times: CONTRIBUTING.md, a Slack pin, and two standups. All three are rung zero on Shingo's ladder — they rely on someone remembering at the exact moment they're rushing. ~50% compliance is roughly what rung zero pays. A fourth reminder gets you a fourth data point.

So the question isn't "what else can I say," it's "what refuses the work."

Also: you bundled two rules that need different devices.

## Formatting — solvable at rung 1 (Control)

Nobody should ever "run the formatter." The machine should have already done it.

```yaml
# .pre-commit-config.yaml  — poka-yoke: unformatted code cannot reach a commit
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.0
    hooks:
      - id: ruff-format          # rewrites the file, doesn't scold you
      - id: ruff, args: [--fix]
```
Plus a committed `.vscode/settings.json` with `"editor.formatOnSave": true`, and `ruff format --check` as a **required** CI check. The hook is for speed; CI is the authority — `--no-verify` exists. Run the same command in both so they can't drift.

## Types — rung 2 (Warning), ratcheted

You can't make untyped Python unwritable, and turning `mypy --strict` on repo-wide gives you 400 errors and a revert by Friday. Gate **changed files only**, so the count can only go down:

```yaml
# .github/workflows/gates.yml
- run: |
    CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD -- '*.py')
    [ -z "$CHANGED" ] && exit 0
    mypy --strict $CHANGED || {
      echo "::error::New code needs type annotations (agreed 2026-08-08 retro)."
      echo "Fix: add annotations to the lines flagged above, or run 'mypy --strict <file>' locally."
      exit 1; }
```
(TypeScript: swap in `tsc --noEmit` + `strict: true`.)

## The part that's actually the enforcement

Neither of the above is a device until **branch protection** marks both jobs required:

```bash
gh api -X PUT repos/OWNER/REPO/branches/main/protection/required_status_checks \
  -f strict=true -f 'contexts[]=format' -f 'contexts[]=types'
```

Without this, you've built a very expensive Slack reminder.

★ Insight ─────────────────────────────────────
The half of the team that complies isn't more disciplined — they installed the tooling once and forgot about it. Compliance tracks *installation*, not *intent*. So make install a no-op: a `make setup` in onboarding, or a CI job that fails if `.pre-commit-config.yaml` hooks weren't run.
─────────────────────────────────────────────────

## Before you call it done

Break it on purpose: push a branch with one badly-formatted, untyped function. Watch both checks go red. Fix, watch green. A gate that has never fired is a rumour.

Then delete the rule from CONTRIBUTING.md and replace it with one line pointing at the workflow file. Leaving the prose there tells new people the rule lives in a document, which is the belief that got you here.

Want me to write these into the repo? Tell me the stack (I assumed Python from "type annotations") and whether you're on GitHub Actions.