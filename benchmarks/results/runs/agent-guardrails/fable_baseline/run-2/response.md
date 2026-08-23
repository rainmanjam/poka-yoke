Nothing is wrong with the wording. The problem is the category: a CLAUDE.md line is training, and training is exactly the thing that fails one time in ten. Capitals and repetition don't change the failure rate because the failure isn't "didn't read it" — it's "read it, then lost it under 80k tokens of other context, or rationalized an exception." Your own repo's first rule covers this: *if the change relies on someone remembering something, it is not finished.*

So stop trying to write a better instruction and put a device in the path that physically can't be skipped. Three layers, cheapest first:

**1. Deny rules in `.claude/settings.json`** — evaluated by the harness, not the model:
```json
"permissions": {
  "deny": [
    "Edit(src/generated/**)",
    "Write(src/generated/**)",
    "Bash(git push --force*)",
    "Bash(git push -f*)"
  ]
}
```
This handles the straightforward cases. It's pattern matching, so `git push origin main --force-with-lease` or `git push -fu` may slip past — which is why you want layer 2.

**2. A PreToolUse hook** that parses the actual command. You already ship one: `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py`. Extend it (or add a sibling) to exit 2 on any Bash input matching `push.*(--force|-f\b|\+refs)` and any Edit/Write/MultiEdit whose path resolves under `src/generated/`. Exit 2 blocks the call and feeds the reason back to the model, so it self-corrects instead of silently retrying.

**3. Git-level, so it holds even when the agent shells out in a way no hook sees** (`sh -c`, a script, a different runtime):
- Branch protection on the remote: "Do not allow force pushes" on `main`. This is the only one that's truly unbypassable from the client.
- Locally: `git config receive.denyNonFastForwards true` on any bare repo you push to, and a `pre-push` hook rejecting non-fast-forward updates.
- For generated files: a `pre-commit` hook that fails if `src/generated/` is staged without the generator having run (compare a checksum against the regeneration output). That catches the edit at commit time regardless of who made it.

Then do what `CLAUDE.md` here asks of every check: break it on purpose. Ask Claude to "add a field to `src/generated/types.ts`" and to "force push this branch," and watch each layer go red. A guard that's never fired is a rumour.

Once the devices exist, you can actually *delete* the caps-lock lines — or reduce them to one sentence explaining why the hook will block it. Instructions that describe a device age fine; instructions that substitute for one don't.

If you want, I can write the hook and the settings block into `assets/devices/claude-hooks/` with the matching/near-miss tests — say the word and I'll do it.