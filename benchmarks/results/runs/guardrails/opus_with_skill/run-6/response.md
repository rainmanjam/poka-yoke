Using **poka-yoke:guardrails** — this is the "we agreed to X and people still don't" case.

## The short answer: nothing. Stop trying to get people to follow it.

Everything you've done — CONTRIBUTING.md, the Slack pin, two standups — is the same device: *training*. Training degrades. Two weeks and ~50% adherence isn't a discipline problem on your team, it's the expected decay curve of a rule that lives in someone's memory. Another reminder, a PR-template checkbox, or a reviewer-checklist item are all the same rung, and will get you the same number.

The two rules also need different devices, because one is auto-fixable and one isn't.

## Formatting — delete the rule instead of enforcing it

Nobody should be *running* the formatter. Make the unformatted state unreachable:

1. **Format on save**, committed to the repo (`.editorconfig` + checked-in editor settings + recommended-extensions file). Removes the human action entirely.
2. **A bot that formats the PR branch on push** (pre-commit.ci, autofix.ci, or a workflow that commits the format). Unformatted PRs stop existing — there's no gate to fail and no one to nag.
3. If you'd rather it fail than autofix: pre-commit hook for speed, plus `--check` as a **required** CI check for authority. The hook alone is not enforcement; `--no-verify` exists.

First, land one repo-wide reformat commit and add its SHA to `.git-blame-ignore-revs`, so the gate never fires on code nobody touched.

## Types — can't be autofixed, so it has to be a gate that ratchets

Turning `mypy --strict` / `tsc --noEmit` on across an existing codebase produces hundreds of errors and gets reverted by Friday — and it teaches everyone that gates are things you bypass, which is worse than never adding it.

Instead: **enforce on changed files only**, or generate a baseline of existing violations and fail only on *new* ones. The count can only go down. Untyped legacy code stays legal; untyped new code stops merging.

Make the failure message teach — name the file, say `run make fmt`, not `error: rule violated`. That's the one moment prose actually works, because someone is guaranteed to read it.

## The piece that makes it real

Branch protection with those jobs marked **Required**. Without it, CI is advisory and you're back to persuasion:

```
gh api -X PUT repos/OWNER/REPO/branches/main/protection/required_status_checks \
  -f strict=true -f 'contexts[]=format' -f 'contexts[]=types'
```

## Then prove it fires

Open a throwaway PR with deliberately unformatted, untyped code. Watch it go red. Fix it. Watch it go green. A gate that has never once failed is a rumour, not a device.

`★ Insight ─────────────────────────────────────`
The rung matters more than the effort: your Slack pin was rung 0 (relies on memory), a reviewer catching it is rung 3 (detection, after the fact, inconsistent), CI is rung 2 (warning, at the moment it happens), and format-on-save is rung 1 (the mistake can't occur). You've been working hard at the bottom of the ladder.
`─────────────────────────────────────────────────`

Tell me the language, CI system, and package manager and I'll write the actual configs — the ratchet script for types is the only non-trivial part.