Nothing wrong with your wording. The problem is the *category* of thing you wrote: a CLAUDE.md line is training, and training degrades — under long contexts, after compaction, and in subagents that never read the file at all. Caps and repetition don't change that; "one time in ten" is exactly what an instruction-only rule looks like. The fix is to move both rules from prose to a device that refuses the call before it runs. Five parts, all needed.

## 1. Deny rules — `.claude/settings.json` (committed, not `.local`)

```jsonc
{
  "permissions": {
    "deny": [
      // poka-yoke: force-push can destroy remote-only commits [control]
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      // poka-yoke: generated files are overwritten on next build; edit the source [control]
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "MultiEdit(./src/generated/**)"
    ]
  }
}
```

This already covers the `src/generated/` rule fully — path globs match the edit tools directly.

## 2. A hook for the force-push rule — patterns aren't enough

Deny strings match the **prefix** of a command. `git push origin main --force`, `git push --force-with-lease`-vs-`--force` distinctions, and `cd x && git push -f` all slip past. That rule needs a `PreToolUse` hook that inspects the command. The plugin ships one: `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` — its regex blocks `--force` and bare `-f` anywhere in a `git push` while deliberately *allowing* `--force-with-lease`. Also catch Bash-based edits to generated files (`sed -i`, `echo >`) — the Edit deny doesn't see those:

```python
# add to RULES in guard_dangerous_commands.py
(r"\bsrc/generated/",
 "src/generated/ is build output and will be overwritten. Edit the schema/source it is "
 "generated from, then re-run the generator."),
```

Wire it in `settings.json`:

```json
"hooks": { "PreToolUse": [{ "matcher": "Bash|Edit|Write",
  "hooks": [{ "type": "command", "command": "python3 .claude/hooks/guard_dangerous_commands.py" }] }] }
```

## 3. The deny message is the real device

The agent reads it and acts on it. A bare refusal produces a workaround — and the workaround for a blocked `Edit` is often `cat > file`, which is worse. Every message must say what was blocked, why, and what to do instead. The template's reasons already have that shape (`guard_dangerous_commands.py:32-33`).

## 4. Location

`.claude/settings.json`, committed. A rule in `settings.local.json` protects one laptop, which is the same failure as the CLAUDE.md line.

## 5. Prove it fires — don't skip this

Ask Claude to `git push --force` and to edit a file in `src/generated/`; confirm the denial *and* that its message appears. Then confirm `git push --force-with-lease` and editing `src/` outside `generated/` still work. An untested hook with a regex that doesn't match the real command string is protection that exists only on paper.

Then delete the two CLAUDE.md lines. What stays in CLAUDE.md should be facts (where the generator lives, how to run it), not rules you hope get followed.

★ Insight ─────────────────────────────────────
- Two rules, two mechanisms: a path rule is a pure string match (deny entry, rung 1); a command rule has variants and a safe sibling (`--force-with-lease`), so it needs logic — a hook.
- The hook fails *open* on bad input on purpose (`guard_dangerous_commands.py:104`): a crashing hook blocks every tool call, which is its own outage.
─────────────────────────────────────────────────

**Recap:** You're not wording it wrong — you're using the wrong rung. Replace the two CLAUDE.md lines with committed deny rules for `src/generated/` and the bundled PreToolUse hook for force-push, with redirecting deny messages, and test both the blocked and the allowed neighbour. I haven't written anything to your repo; say the word and I'll install the `settings.json` + hook into the target project.