Using poka-yoke:agent-guardrails. One sentence of diagnosis, then the fix.

## The diagnosis

Nothing is wrong with your prose — caps and repetition are still *training*, and training has a failure **rate** where an irreversible action needs a failure **mode**. 90% compliance on force-push isn't 90% protection; it's a force-push every ten sessions. The specific 10% is predictable: after compaction the middle of CLAUDE.md is the first thing summarized away, subagents often never read it at all, and a rejected non-fast-forward push is exactly the moment the model reaches for the shortest path to "working."

Your two rules need *different* devices, which is the part that usually gets missed.

## `src/generated/` — a deny rule is enough

Pure path match. But it must cover every write tool, not just Edit:

```jsonc
// .claude/settings.json
{
  "permissions": {
    "deny": [
      // poka-yoke: generated files are outputs, not sources [control]
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "MultiEdit(./src/generated/**)"
    ]
  }
}
```

Then add a header line to the generated files themselves — the agent reads the file before editing it, so that's a second, independent shot at the same hazard.

## Force-push — a deny rule here fails open

`"Bash(git push --force:*)"` is prefix-matched. It catches `git push --force origin main` and silently misses `git push origin main --force`, `git push -f`, and `git push origin +main`. That's the dangerous kind of device: it looks installed and isn't. Use a hook:

```python
# .claude/hooks/guard.py  — poka-yoke: blocks irreversible git ops [control]
import json, re, sys
try: p = json.load(sys.stdin)
except Exception: sys.exit(0)          # fail open; a crashing hook blocks all tool use
if p.get("tool_name") == "Bash":
    cmd = p.get("tool_input", {}).get("command", "")
    if re.search(r"\bgit\s+push\b.*(--force(?!-with-lease)|(?<![\w-])-f(?![\w-])|\s\+)", cmd):
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason":
              "[poka-yoke] Force-push destroys commits that exist only on the remote. "
              "Use --force-with-lease if you must rewrite, and ask before rewriting shared "
              f"history. Blocked: {cmd[:200]}"}}, sys.stdout)
sys.exit(0)
```

Wire it up alongside the permissions block:

```jsonc
"hooks": { "PreToolUse": [{ "matcher": "Bash",
  "hooks": [{"type": "command",
             "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py\""}] }] }
```

The message matters as much as the deny — a bare refusal produces a creative workaround, usually worse. This one names what was blocked, why, and the safe alternative.

**Commit both files.** `.claude/settings.local.json` protects one laptop, which is the same failure as documenting it.

## Prove it fires — this is the step people skip

```
git push --force-with-lease origin feat/x   → must still work
git push origin main --force                → must deny (the case the pattern misses)
echo x >> src/generated/api.ts              → must deny via Bash too
```

Then delete `src/generated/` from CLAUDE.md. Leaving it there teaches you the rule is enforced by prose.

★ Insight ─────────────────────────────────────
- Claude Code permission patterns are **prefix** matches, not substring — flag-after-argument forms slip through. Anything where argument order varies needs a hook, not a deny string.
- `sys.exit(0)` on malformed input is deliberate: a hook that crashes denies *every* tool call, turning a guardrail into an outage.
- Deny rules run before the tool; the model never sees the action succeed, so there's no partial-damage window.
─────────────────────────────────────────────────

**One thing I can't decide for you:** `src/generated/` still has to be *writable by something* — your codegen runs through Bash, and the hook above doesn't gate Bash writes to that path. Blocking all of them breaks regeneration; blocking none leaves `sed -i src/generated/…` open.

In `.claude/hooks/guard.py`, add the branch that distinguishes them — roughly:

```python
# Bash writes into src/generated/ are legitimate only from the generator.
# ~5 lines: allow if cmd starts with your codegen entrypoint, deny otherwise.
```

You know whether that's `make codegen`, `pnpm generate`, `protoc`, or a script path — and whether allow-listing a command prefix is safe in your repo or too easy to spoof. Tell me the entrypoint and I'll wire it in and write the files.