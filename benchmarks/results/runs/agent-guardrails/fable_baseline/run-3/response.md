Nothing wrong with the wording — you've hit the thesis of this very repo: instructions degrade, devices don't. Caps and repetition don't change the failure mode. CLAUDE.md is *training*: it lives in context, competes with everything else in context, and gets compacted, deprioritized, or reasoned around ("this is the generated file the user clearly wants fixed"). A 10% miss rate on a soft instruction is about what you should expect, and doubling the text won't move it much.

The fix is to move both rules out of the model's judgement and into the harness and into git, so they can't be forgotten:

**1. Permission deny rules (`.claude/settings.json`)** — the harness blocks the tool call before Claude acts:
```json
{
  "permissions": {
    "deny": [
      "Edit(src/generated/**)",
      "Write(src/generated/**)",
      "Bash(git push --force*)",
      "Bash(git push -f*)"
    ]
  }
}
```
Caveat: Bash deny patterns are prefix matches. `git push origin main --force`, `--force-with-lease`, `git push -f` chained after `&&` — all slip through. So deny rules are a first layer, not the device.

**2. A PreToolUse hook** that actually parses the command — this is the real guard on the agent side. Script reads the tool input from stdin, exits 2 with a message if the Bash command contains `--force`/`-f` after `git push`, or if an Edit/Write/MultiEdit path resolves inside `src/generated/`. This catches the chained and reordered forms the deny patterns miss. The repo already ships a template for this shape under `plugins/poka-yoke/assets/devices/claude-code/`, and `/hookify` can generate one from your transcript.

**3. Git-level enforcement, which holds across every runtime and for humans too:**
- Branch protection on the remote: "allow force pushes" off. Then force push *cannot succeed* — no hook needed, nothing to remember.
- A pre-commit hook (or a CI check) that fails if any staged path is under `src/generated/` and was not produced by the generator. Better still, make the generator's output reproducible and have CI regenerate and `git diff --exit-code` — then a hand edit fails the build, with a message saying what to do instead.

Layer 3 is the one that matters most: it works when Claude is not in Claude Code, when a contributor doesn't read CLAUDE.md, and when you yourself are tired.

Then apply the repo's own rule — prove each check can fail. Hand-edit a generated file and watch CI go red; try `git push -f` to a scratch branch and watch the remote reject it. A guard that has never gone red is a rumour.

Finally, once the devices are in place, *shorten* the CLAUDE.md entry to one line pointing at the device ("generated files are enforced by CI — run `make generate`"). Long shouty instructions push other useful context out of the window without buying compliance.

If you'd like, I can add the settings deny rules and a PreToolUse hook script to this repo's `assets/devices/claude-code/` and a pre-push/pre-commit pair under `assets/devices/git/`, each with the "break it on purpose" test.