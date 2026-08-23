You've discovered the exact problem poka-yoke is built around: **instructions degrade, devices do not.**

What's happening at the 10% mark is predictable. Instructions are read once at session start, then compressed out of the active context window as your conversation lengthens. By hour 2-3, the CLAUDE.md is in the archived/compressed section—Claude "knows" the rule exists but doesn't surface it during decision-making. Caps and repetition don't fix this; they just make the training stronger, not the device.

Convert your instructions into **git hooks** instead:

```bash
# .git/hooks/pre-commit (make executable: chmod +x)
#!/bin/bash
if git diff --cached --name-only | grep -q '^src/generated/'; then
  echo "ERROR: Do not edit files in src/generated/"
  exit 1
fi
```

```bash
# .git/hooks/pre-push (make executable: chmod +x)
#!/bin/bash
if git push --dry-run 2>&1 | grep -q 'force'; then
  echo "ERROR: Force push is forbidden"
  exit 1
fi
```

Then remove those rules from CLAUDE.md—or reframe them as "why these devices exist" rather than "do this or else."

The reason this project has 20+ checks in `.github/workflows/validate.yml` isn't paranoia; it's that every one of them caught something that instructions alone had missed. Same principle applies to your local workflow.

If you want Claude to respect instructions at all, they need to be either:
1. **Checked before action** (hooks, linters, validation—the device catches it)
2. **In active context** (early in conversation, not compressed away)
3. **Scoped narrowly** (not "never" but "when running deploy, don't...") 

Right now you have #1 failing and #2/#3 getting weaker as context grows. Hooks + removing the instruction from CLAUDE.md will fix it permanently.