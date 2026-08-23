Short answer: you're not doing anything wrong with the *wording*. You're using the wrong *kind* of control. CLAUDE.md is advice; caps and repetition don't change its category.

## Why ~10% leaks through

CLAUDE.md is a system-prompt instruction. It fails in predictable situations, none of which are fixed by louder text:

1. **Context compaction** — long sessions get summarized; the summary may drop or soften your rule.
2. **Subagents** — a spawned agent gets a fresh context; your CLAUDE.md may not be in it at all.
3. **Goal pressure** — "the rebase left diverged history, the obvious fix is `push --force`" / "the generated file is the one with the bug, just patch it." The model reasons its way to the action as the *helpful* thing.
4. **Caps/repetition fatigue** — everything shouted reads as background noise; it doesn't raise priority, it just lowers signal.

In poka-yoke terms, you built a warning sign and are surprised it isn't a lockout. A 90% control is what a sign gets you.

## What actually fixes it

Move each rule down to a layer that doesn't depend on the model remembering:

**Force push**
- `~/.claude/settings.json` → `permissions.deny`: `Bash(git push --force*)`, `Bash(git push -f*)`. The harness blocks it before execution, regardless of context state. (Decide whether `--force-with-lease` is also banned — this is the one judgment call.)
- GitHub branch protection on `main` → "Allow force pushes" off. Server-side; survives any client, any agent, any human.

**`src/generated/`**
- `permissions.deny`: `Edit(src/generated/**)`, `Write(src/generated/**)`.
- A header comment in each generated file (`// GENERATED — edit the schema in X and run Y`). This catches the "I read the file, it looks editable" case and tells the model the correct move instead of just "no."
- CI check that regenerates and fails on diff. Catches anything that got through anyway.

Keep the CLAUDE.md lines — once, lowercase, with the *why* and the *alternative* ("generated from `schema/`; run `npm run codegen` instead"). A rule with an escape route gets followed more than a bare prohibition, because the model under pressure has somewhere to go.

`★ Insight ─────────────────────────────────────`
The general principle: instructions in a prompt are **training-level** controls — they shape tendency. Deny rules and branch protection are **mechanism-level** — they make the wrong action impossible. Anything you'd fire someone for belongs at mechanism level; the prompt is for taste, not safety.
`─────────────────────────────────────────────────`

If you want, I can write the `settings.json` deny block and a `gh api` call for the branch protection — tell me whether `--force-with-lease` should stay allowed.