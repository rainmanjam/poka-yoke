Using **poka-yoke:guardrails** — the ask is enforcement of an agreed rule, not documentation of it.

## The diagnosis

Everything you've tried — CONTRIBUTING.md, the Slack pin, two standup mentions — is the same device: **rung 0, training**. Not a weak version of enforcement; not enforcement at all. ~50% compliance after two weeks is the normal, expected yield of rung 0. Adding a third reminder gets you a third sample from the same distribution.

The finding to write down is about the pipeline, not the people: *nothing in the path from keyboard to merge can tell the difference between a formatted, typed PR and an unformatted, untyped one.*

## Treat the two rules differently — they're not the same hazard

**Formatting is Control (rung 1), and you should never gate it.** A formatter is deterministic and auto-fixing, so don't reject unformatted code — *rewrite it*. Two places, same tool:

- Editor: `formatOnSave` + a committed editor config, so it's fixed before it's ever a diff.
- Pre-commit hook that runs the formatter and re-stages. The commit comes out formatted whether or not anyone remembered.
- CI runs the identical command in `--check` mode as the authority behind the bypassable hook.

Once the formatter rewrites rather than complains, "unformatted PR" stops being a thing someone can do.

**Types can't be auto-fixed, so it's rung 2 (Warning) plus a ratchet.** This is where teams blow themselves up: turning `mypy --strict` / `tsc --noEmit` on across an existing codebase yields hundreds of errors, everyone learns to bypass gates, and it's reverted by Friday. Instead, enforce on **changed files only**, or generate a baseline of today's errors and fail only on *new* ones. The count can only go down.

`★ Insight ─────────────────────────────────────`
The retro rule "add type annotations to **any new code**" is already a ratchet in prose. A baseline file makes it a ratchet in the pipeline — same policy, no memory required.
`─────────────────────────────────────────────────`

## The piece that actually makes it enforcement

Neither hook matters until both jobs are **required checks under branch protection**. Without that, CI is advisory and you're back to rung 0 with extra YAML. That's a repo-settings change (or a `gh api` call) — I can hand you the exact command, but you have to run it.

## Before you call it done

Open a PR with deliberately unformatted, untyped code. Watch it go red. Confirm the failure message names the exact command to fix it — a gate that says `error: rule violated` produces a workaround, not a fix. Then fix it and watch it go green.

## What I need from you

Two things and I'll write the configs:

1. **Stack** — Python (`ruff format` + `mypy`) or TS (`prettier` + `tsc`), or something else?
2. **Ratchet policy** — this one's your call, and it shapes how the team experiences the gate: *changed-files-only* (simple, but a touched legacy file suddenly demands annotations) or *error baseline* (more setup, never surprises anyone).