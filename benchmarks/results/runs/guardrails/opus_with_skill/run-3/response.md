Using **poka-yoke:guardrails** — this is exactly the case it names: *"we agreed to X and people still do not."*

## The short answer: nothing

You've now delivered the same rule through three channels. CONTRIBUTING.md, a pinned Slack message, and two standups are all the same device — **training** — and the 50% number is the measurement of how well training works. A fourth channel gets you 50%. Shingo's whole point is that this isn't a people problem to solve harder; it's a signal that the rule was never wired to anything.

Rung 0 (docs, reminders, review checklists) → you need rung 1 (impossible) or rung 2 (announced at the moment it happens).

## Your two rules need different devices

**Formatting is a rung-1 problem, and the fix is to delete the human step.** Nobody should "run the formatter" — the machine should. Three layers, cheapest first:

1. Commit the editor config (`.vscode/settings.json` with `formatOnSave`, or `.editorconfig`) so it happens invisibly.
2. Pre-commit hook that **auto-fixes and re-stages**, not one that scolds.
3. CI check as the authority, because `--no-verify` exists.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit   # or prettier/biome for TS
    rev: v0.6.9
    hooks: [{id: ruff-format}]
```

**Type annotations can't be auto-fixed, so it's a ratchet problem.** Turning `mypy --strict` on across an existing codebase produces hundreds of failures and gets reverted by Friday — and that reversal teaches everyone that gates are negotiable, which is worse than where you are now. Enforce on **changed files only**. The violation count can then only go down, and nobody is blocked by code they didn't write.

```yaml
# CI job — the required check
- name: types (changed files only)
  env: {BASE_REF: "${{ github.base_ref || 'main' }}"}
  run: |
    git diff --name-only --diff-filter=ACM "origin/$BASE_REF"...HEAD -- '*.py' \
      | xargs -r mypy --strict --
```

## Then the part that's actually load-bearing

**Branch protection with these as required checks.** Without it, both jobs are advisory and you've built a more elaborate reminder. This is the one step you probably can't do from a config file:

```bash
gh api -X PUT repos/OWNER/REPO/branches/main/protection/required_status_checks \
  -f strict=true -f 'contexts[]=format' -f 'contexts[]=types'
```

**Make the failure teach.** `error: rule violated` produces a workaround. `Unformatted files. Run: ruff format . — or enable format-on-save so this never fires again` produces a fix and one fewer future failure.

**Prove it fires.** Push a deliberately unformatted, untyped file. Watch both checks go red. Fix it, watch them go green. A gate that's never been red is a rumour.

Finally: replace the CONTRIBUTING.md paragraph with one line pointing at the checks. Leaving the prose in implies the rule still depends on reading it.

---

**Two things I'd need from you to make this concrete:**

1. **Stack?** I wrote Python (ruff/mypy); the shape is identical for prettier/`tsc --noEmit`.
2. **The ratchet policy is the real design decision** — changed-files-only (simple, but a heavily-edited legacy file suddenly demands full annotation) versus a committed baseline count that must monotonically decrease (kinder to legacy files, one more artifact to maintain). Which failure mode does your team tolerate better?