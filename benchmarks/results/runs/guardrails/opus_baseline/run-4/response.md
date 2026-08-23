## What you've tried is four instances of the same thing

CONTRIBUTING.md, the Slack pin, standup twice — all rung zero. They're training, and training degrades on roughly a two-week half-life, which is exactly the number you observed. A fifth reminder will produce the same 50%.

The other tell: the violation is being discovered at PR review. That's the last station. Move detection to the keystroke.

## The devices, in order

**Formatter — don't check it, apply it.** Nobody should be remembering to run it. Two layers:

- Format-on-save in the shared editor config (`.vscode/settings.json` committed, or `.editorconfig` + repo-local config). Most violations disappear here.
- Pre-commit hook with `--fix` so the unformatted state is not committable. The template this repo ships uses `ruff-format` + `ruff-check --fix --exit-non-zero-on-fix`; the commit either succeeds formatted or fails loudly. That's rung 1, control: the mistake stops being possible rather than being caught.

**Types — can't be auto-fixed, so gate it.** `mypy` (or `tsc --noEmit`) as a **required** CI check. Rung 2, warning, and control isn't available because no tool can infer the annotation you meant.

**Branch protection.** Without required checks configured on the branch, none of the above is enforcement — it's a suggestion with a red X. This is the piece that actually changes the 50%, and it's the one you have to click yourself.

## The failure mode to avoid

Turning on `mypy --strict` across an existing repo yields hundreds of errors and gets reverted by Friday — and worse, it teaches everyone that gates are things you bypass. **Ratchet instead:** run the type check only on files changed in the PR, or generate a baseline of current violations and fail only on new ones. The count can only go down. Same for the formatter: don't reformat the world in one commit, or every future `git blame` gets harder and people will hold that against the device.

Second rule: make the failure message teach. `error: type annotation missing` produces a workaround. `Add a return annotation to parse_order() — run 'make types' locally to see this before pushing` produces a fix.

## Then delete the CONTRIBUTING.md line

Or rewrite it to describe the device rather than the obligation. Leaving a written rule next to a mechanical one teaches that written rules are the optional kind.

**Prove it fires before you trust it:** open a PR with a deliberately unformatted, unannotated function, watch it go red, fix it, watch it go green. A check that's never once failed is a rumour.

`★ Insight ─────────────────────────────────────`
The formatter and the type rule look like one policy but sit on different rungs. Formatting is mechanically derivable, so it can reach *control* — the bad state is unreachable. Annotations require intent, so the best available rung is *warning*. Saying that out loud is what stops someone later asking "why isn't mypy auto-fixing too."
`─────────────────────────────────────────────────`

Want me to write the actual `.pre-commit-config.yaml`, CI workflow, and the changed-files-only type check? I'll need to know the stack — I've assumed Python/ruff/mypy above; swap in Prettier/`tsc` if it's TypeScript.