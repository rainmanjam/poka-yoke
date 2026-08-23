Using **poka-yoke:guardrails** — you have a rule that needs enforcing, not documenting.

## The diagnosis

CONTRIBUTING.md, a Slack pin, and two standup mentions are the same device three times: **training**. On the regulatory ladder that's rung zero — it relies on someone remembering. ~50% compliance after two weeks is exactly what rung zero produces. Nothing is wrong with your team; the agreement has no device behind it.

Two rules, two different ceilings:

**Formatting is a Control-rung problem.** It's mechanically fixable, so don't check it — *do* it. A pre-commit hook that runs the formatter and rewrites the file means unformatted code cannot be committed; there's nothing for anyone to remember or forget.

```yaml
# .pre-commit-config.yaml  — poka-yoke: unformatted code cannot be committed
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit   # or prettier for TS
    rev: v0.6.9
    hooks: [{id: ruff-format}]
```

Pair it with a committed editor config (`.vscode/settings.json` with `formatOnSave`) so most people never even see the hook fire.

**Type annotations top out at Warning.** They can't be auto-generated, so the device is a CI check that refuses the merge — `mypy` / `tsc --noEmit` as a **required** status check.

## The piece that actually does the work

`--no-verify` exists and people under deadline use it. The pre-commit hook buys speed; **branch protection with required checks** buys authority. Run the same script in both so they can't drift. Without required checks, a red CI job is a suggestion — this is the step most teams skip, and it's the whole device:

```bash
gh api -X PUT repos/:owner/:repo/branches/main/protection/required_status_checks \
  -f strict=true -f 'contexts[]=format' -f 'contexts[]=types'
```

## Install it so it doesn't get ripped out

Turning strict typing on repo-wide gives you 400 failures and a revert by Friday — and worse, it teaches everyone to bypass gates. **Enforce on changed files only** (`git diff --name-only origin/main...HEAD`), so the untyped-file count can only go down. And write the failure message to teach: name the file, say why, give the exact fix command.

## Then prove it fires

Push a branch with a deliberately unformatted, untyped file. Watch the gate go red. Fix it, watch it go green. Show the team both. A gate nobody has seen fail is a rumour, not a device.

`★ Insight ─────────────────────────────────────`
The retro itself is the deeper hazard. "Everyone agreed to X" is a rung-zero output by construction. The better retro question is *"what device would have caught this?"* — if the answer is a person remembering, the item isn't done.
`─────────────────────────────────────────────────`

**Two things I need from you to write these files:**

1. **Stack** — Python (ruff + mypy) or TypeScript (prettier + tsc)? Something else?
2. **The ratchet policy** — a real trade-off worth your call: *changed-files-only* (zero friction, slow convergence) vs. *a checked-in baseline of existing violations that can only shrink* (visible progress, but merge conflicts on the baseline file). Which fits your team's tolerance?