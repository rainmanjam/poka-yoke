Short answer: CLAUDE.md text is a *prompt*, not a *rule*. No matter how many times you write it or how loud you shout it in caps, it's still just tokens competing with everything else in context — over a long session it can get diluted, summarized away, or simply outweighed by the immediate task at hand. "Follows it 9/10 times" is actually about what you should expect from a soft instruction.

To make these two *actually* unbreakable, move them from "instruction the model reads" to "rule the harness enforces" — that happens outside the model's control entirely:

**1. Never force push** → deny it in permissions (`.claude/settings.json`):
```json
{
  "permissions": {
    "deny": [
      "Bash(git push --force*)",
      "Bash(git push -f*)"
    ]
  }
}
```
This blocks the tool call before it ever runs — the model can't talk its way around it, and no context window pressure will erode it.

**2. Never edit files in src/generated/** → this one's trickier since Edit/Write don't have a path-based deny syntax as clean as Bash's glob, so the more reliable route is a `PreToolUse` hook that inspects the tool input and exits nonzero (blocking) when the path matches `src/generated/`. That's a small script, but it's deterministic — it runs every single time, unconditionally, regardless of what's in context.

Both of these are exactly what the `update-config` skill is meant to set up (it configures `settings.json` permissions and hooks), but the skill invocation just errored out on my end rather than returning instructions. Want me to write the actual hook script and permissions block by hand instead? I'd need to know:
- Is `src/generated/` a fixed path, or could there be multiple generated dirs to guard?
- Do you want force-push blocked entirely, or just want a confirmation prompt (e.g. allow with `--force-with-lease` but block bare `--force`)?