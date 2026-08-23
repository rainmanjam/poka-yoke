Instructions to an agent are rung zero (training), and training degrades. A line in `CLAUDE.md` saying "never do X" is not a device; it is a request the agent will eventually ignore as context length grows or subagents are spawned.

To actually stop these behaviors, you must replace the instructions with devices that block the actions before they execute. Here are the five steps to do that for your two rules:

### 1. The deny rule, with real syntax
For your generated files, you can block the agent from editing them entirely using `permissions.deny`.
```jsonc
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)"
    ]
  }
}
```

### 2. A hook where a pattern is not enough
The `settings.json` deny rules only match the *start* of a command. This means `"Bash(git push --force:*)"` will catch exactly that, but it will miss a command like `git push origin main -f`. 

Therefore, your **generated files rule** works perfectly as a pattern, but your **force push rule** requires a `PreToolUse` hook script that can inspect the command with a regex to reliably catch the flag anywhere in the string (while safely allowing `--force-with-lease`).

### 3. What the deny message says
When blocking an action, the deny reason *is* the device. A bare "denied" makes the agent try to find a creative workaround. The message must name what was blocked, why, and what to do instead.
*For the push hook:* "Force-push can destroy commits. Use `--force-with-lease` if you must rewrite, or ask the user to run it."

### 4. Where the config lives
Put these rules in `.claude/settings.json` and commit it to the repository. This ensures it applies to every agent session. A rule in `settings.local.json` only protects one machine, which is the same failure mode as documenting it.

### 5. Proof that it fires
Once installed, you must verify the devices. Ask the agent to edit a file in `./src/generated/` and separately ask it to run `git push origin main -f`. Confirm that both are blocked *and* that the agent reads the reason. An unverified device is worse than no device, because it creates confidence without protection.