One-sentence diagnosis: **CLAUDE.md text is rung-zero — training that degrades under long contexts, compaction, and subagents that never read the file — so a 1-in-10 failure rate isn't a fluke, it's what instructions do by default.** The fix isn't wording it more forcefully; it's moving both rules out of prose and into something the tool boundary enforces, which is *control* rather than *hope*.

Here's the replacement, both rules:

**1. Deny rules — `.claude/settings.json` (committed, not `settings.local.json`)**
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
This alone should kill most of the force-push failures — that's the tool-boundary Control rung.

**2. A hook, because a pattern isn't enough for `src/generated/`**
The `Edit`/`Write` deny only fires on those two tools. Nothing stops the agent writing into `src/generated/` via `Bash` — `sed -i`, `echo > file`, a heredoc. This repo already ships `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py`, which does exactly this pattern for `.env`; it needs a second check block for `src/generated/`, and its force-push regex (handles both `--force` and `-f`, allows `--force-with-lease`) covers your other rule too — worth wiring in even with the deny rule above, since the hook can also catch `git push -f` issued through a wrapper script the deny-string wouldn't match.

**3. The deny message** (this is what stops the workaround, not the refusal):
> Blocked: `src/generated/` is generated output — edits here are silently overwritten on the next build. If the generator itself is wrong, fix the source template; if the generator is missing a case, that's the change to make.

**4. Verify it actually fires** — untested hooks fail open silently:
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py
# expect: permissionDecision "deny"

echo '{"tool_name":"Edit","tool_input":{"file_path":"src/generated/foo.ts"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py
# expect: permissionDecision "deny" once the check is added
```
Then confirm the neighboring legitimate action still works (`git push origin main`, editing a non-generated file) — a rule that blocks everything is as broken as one that blocks nothing.

Want me to write the `settings.json` deny block and add the `src/generated/` check to `guard_dangerous_commands.py`, wire it into `.claude/hooks/`, and run the verification commands above? I won't touch anything until you say go.