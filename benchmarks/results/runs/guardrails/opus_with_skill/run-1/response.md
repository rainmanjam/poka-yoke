## The short answer: nothing in that category will work

CONTRIBUTING.md, a Slack pin, and two standup mentions are three instances of the same device — **training**. In Shingo's ladder they're rung 0: they rely on someone remembering at the moment of the commit. ~50% compliance after two weeks isn't a people problem, it's the expected decay rate of a rule with no device behind it. A fourth reminder gets you the same number.

So the question to answer instead: *what makes an unformatted or untyped PR unable to reach main?*

`★ Insight ─────────────────────────────────────`
Formatting and typing need **different rungs**. Formatting can reach rung 1 (Control) because a machine can just do it — nobody should be "remembering to run the formatter." Typing can't be made impossible to omit at write time, so it lands at rung 2 (Warning): possible to write, impossible to merge.
`─────────────────────────────────────────────────`

## Formatting — stop asking, start doing

Don't gate on "did you format." Format it for them:

1. Commit the editor config (`.editorconfig` + `.vscode/settings.json` with format-on-save) so most of it never happens.
2. Pre-commit hook runs the formatter in **write** mode on staged files — it fixes and restages rather than failing. Fast, no friction, nothing to remember.
3. CI runs the same formatter in **check** mode as a required check. This is the actual enforcement; the hook is just for speed.

Run the identical script in both so they can't drift. Never rely on the hook alone — `--no-verify` exists and people under deadline use it.

## Types — ratchet, don't flip the switch

Turning `mypy --strict` / `tsc --strict` on across an existing repo yields hundreds of failures and gets reverted by Friday, which teaches everyone that gates are things you route around. Instead:

- Generate a **baseline** of existing violations, or enforce on **changed files only** (diff against the base ref).
- Fail only on *new* untyped code. The violation count can only go down.
- Required check + branch protection. Without branch protection, a CI workflow is advisory and the whole device is inert.

## Three things that decide whether it survives

**Make the failure message teach.** `error: rule violated` produces a workaround. `src/api.py:42 — new function without annotations. Run 'make types' to see all findings; annotate or add to baseline with a comment saying why.` produces a fix. This is the one place prose belongs.

**Prove it fires.** Push a deliberately unformatted, untyped function, watch the check go red, then fix it and watch it go green. A check that has never once gone red is a rumour.

**Delete the CONTRIBUTING.md paragraph** — replace it with one line pointing at the gate. Leaving both means the doc is what people argue about in review.

---

Two things I need before I can write the actual config:

1. **Stack** — "type annotations" reads as Python (`ruff format` + `mypy`) but could be gradual TypeScript. Which is it, and is CI GitHub Actions?
2. **Ratchet policy** — this one's yours to call: *changed-files-only* (simple, but a heavily-edited legacy file becomes a slog) vs. *baseline file* (existing debt frozen explicitly, visible, and shrinkable — but someone has to regenerate it). Your codebase's age and how much untyped code exists decides it.

Give me those and I'll produce the workflow, the pre-commit config, and the failing-then-passing demonstration.