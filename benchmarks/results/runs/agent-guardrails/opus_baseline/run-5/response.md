Using **poka-yoke:agent-guardrails**. Quick note first: this repo has no `.claude/settings.json` and no `src/generated/`, so the rules you're describing live in another repo — I'll give you paste-ready config and can write it directly if you point me at the path.

## The short diagnosis

Nothing is wrong with your wording. CLAUDE.md is **training, not enforcement** — it's text in a context window that gets compacted, out-competed by the immediate task, and never read at all by subagents. Caps and repetition raise salience slightly; they don't change the category. One-in-ten is roughly what a well-written instruction gets you. The fix is to stop editing the prose and move both rules to the tool boundary.

## 1. Deny rules — `.claude/settings.json`, committed

```jsonc
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(git push --force-with-lease:*)"
    ]
  }
}
```

Committed, not `settings.local.json` — a rule on one machine is the same failure as a rule in a doc.

## 2. Where patterns aren't enough

Both of your rules have a flank the pattern misses:

- **`src/generated/`** — `Edit`/`Write` denies are exact and solid, but Bash routes around them: `sed -i`, `npm run codegen > src/generated/api.ts`, `cp`.
- **force-push** — deny matches the command prefix. `cd web && git push -f`, or a push whose refspec starts with `+` (`git push origin +main`), doesn't match.

So add a `PreToolUse` hook on `Bash` that inspects the full command string:

```python
#!/usr/bin/env python3
# poka-yoke: prevents force-push and Bash-side writes into src/generated/
import json, re, sys

cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")

def deny(msg):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": msg}}))
    sys.exit(0)

if re.search(r"\bgit\s+push\b", cmd) and re.search(r"(--force|-f\b|\s\+\w)", cmd):
    deny("Blocked: force-push. It can destroy commits other people or CI depend on, "
         "and it is not recoverable from this repo. Push normally; if history really "
         "must be rewritten, stop and ask the user to run it themselves.")

if "src/generated/" in cmd and re.search(r">|>>|\b(sed -i|cp|mv|rm|tee)\b", cmd):
    deny("Blocked: writing to src/generated/. Those files are produced by codegen and "
         "your edit will be erased on the next run. Change the schema/template the "
         "generator reads, then re-run codegen.")
```

Wire it up under `"hooks": {"PreToolUse": [{"matcher": "Bash", ...}]}` in the same settings file.

## 3. The deny message is the load-bearing part

This is the step people drop. A bare "denied" makes the agent invent a workaround — often worse (`git push --delete` then re-push). Each message above names **what** was blocked, **why** it's irreversible, and **what to do instead**. That's the one place prose still works, because it arrives exactly when the agent is deciding.

## 4. Prove it fires

Untested hooks fail open constantly — a regex that never matches looks identical to protection. For each rule, run the blocked action and confirm both the denial *and* the message, then run the neighbouring legitimate action (`git push`, editing `src/api.ts`) and confirm it still works.

★ Insight ─────────────────────────────────────
Your two rules aren't the same shape. "Never edit `src/generated/`" is a **path predicate** — Edit/Write denies enforce it exactly, and the residual risk is only the Bash flank. "Never force push" is a **command predicate** over free-form shell, where the space of equivalent phrasings is unbounded; a hook that parses is strictly better than a prefix pattern. The failure rate you're seeing is probably not uniform across the two.
─────────────────────────────────────────────────

★ Insight ─────────────────────────────────────
`--force-with-lease` is in the deny list above, which is a judgment call worth making deliberately — it's meaningfully safer than `--force` (it refuses if the remote moved). Denying it is the conservative read; allowing it keeps a legitimate rebase workflow open. Decide by whether your branches are ever shared mid-flight.
─────────────────────────────────────────────────

**One thing I'd like your input on** — step 3, the deny messages. I wrote generic ones, but the redirect line only works if it names *your* actual path. For `src/generated/`: is it a codegen step the agent can run itself (`npm run codegen`? `prisma generate`?), or something that only happens in CI? Tell me the real command and I'll put it in the message, then write the settings file and the hook into whichever repo this is.