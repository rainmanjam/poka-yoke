You're not doing anything wrong with the prose. The prose is the wrong instrument.

CLAUDE.md is training. It degrades under compaction (long sessions drop it), under subagents (they never read it), and under caps-lock salience decay. Repeating it twice raised the hit rate; it can't reach 100%. **A control that holds 9 times in 10 against an irreversible action isn't a 90% control — it's a broken one that looks like it works.** Force-push and generated-file corruption are exactly the class you never gate with instructions.

Here's the replacement. Both rules need different devices.

## 1. Deny rules — `.claude/settings.json`, committed

```jsonc
{
  "permissions": {
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

Committed, not `settings.local.json` — a rule on one machine is the same failure as documenting it.

## 2. Where the pattern isn't enough

`Bash(git push --force:*)` is a **prefix** match. `git push origin main --force` sails straight through it. That single gap is most of your remaining 10%. Force-push needs a regex hook; the lookahead matters so `--force-with-lease` stays allowed:

```python
(r"\bgit\s+push\b.*(--force(?!-with-lease)|(?<![\w-])-f(?![\w-]))", REASON)
```

`plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` already ships this. Copy it to `.claude/hooks/` in your repo (hooks resolve against the project, not the plugin cache), and wire it with a `PreToolUse` matcher of `Bash|Edit|Write|Read`.

`src/generated/**` is genuinely just a path — the deny rule holds. But note it blocks *tool-level* edits, not `npm run codegen`, which is what you want: the generator still runs, the agent's hand-edits don't land. Back it with a CI job that regenerates and diffs, since Bash `sed` can still route around the tool boundary.

## 3. The message is the device

A bare denial produces a creative workaround, often worse. Deny rules give no custom text — that's the second reason to prefer the hook:

> Blocked: `src/generated/` is codegen output; hand edits are erased on the next run. Change the schema/template it's generated from, then run `npm run codegen`.

## 4. Prove it fires

Untested hooks fail open more than people expect. On a scratch branch:

| Run | Expect |
|---|---|
| `git push --force` | denied |
| `git push origin main --force` | **denied** ← this is the one that catches a naive config |
| `git push --force-with-lease` | allowed |
| Edit `src/generated/api.ts` | denied |
| Edit `src/app.ts` | allowed |
| `npm run codegen` | allowed |

Row 2 red and rows 3/6 green is the whole test. A device that's never gone red is a rumour.

★ Insight ─────────────────────────────────────
The deny rule and the hook aren't redundant — the rule is fast and declarative but string-shaped; the hook reads the actual command. Your two rules split cleanly along that line: one is a path (rule suffices), one is a command with free argument order (needs logic).
─────────────────────────────────────────────────

One decision shapes the rest, and it's yours: **what's the legitimate escape hatch when the schema genuinely changes and a human must hand-edit generated output?** Options are (a) no hatch — regenerate only, (b) the human does it outside the agent session, (c) a `poka-yoke:allow-generated-edit` marker the hook checks for. (a) is strongest and (c) is the one that quietly rots. Tell me which, plus the paths beyond `src/generated/` you want frozen, and I'll write the settings and hook files for you to review before they land — hooks execute code on your machine on every tool call, so you see them first.