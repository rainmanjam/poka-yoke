Nothing wrong with your wording — the problem is the mechanism. CLAUDE.md text is prose that gets weighed probabilistically alongside everything else in context (tool output, conversation history, other instructions). Caps and repetition nudge that weighting up, but they don't make it a rule the harness enforces — it's still just something the model has to *remember* to apply on every single tool call, and with enough context volume or a long session, that recall occasionally loses.

This is actually the exact failure mode this repo's own CLAUDE.md calls out: "If your change relies on someone remembering something, it is not finished." A prose instruction is training; training degrades. What you want instead is a device — something that fails deterministically, not probabilistically.

For these two specific rules, that means **hooks**, not prose:
- A `PreToolUse` hook that denies `Edit`/`Write` when the path matches `src/generated/**`
- A `PreToolUse` hook that denies `Bash` when the command matches `git push --force` / `push -f`

Those run outside the model's judgment entirely, so there's no "maybe" — the tool call is blocked before it executes, every time.

Want me to set these up? The `update-config` skill (or `hookify`) can wire both into `.claude/settings.json`.