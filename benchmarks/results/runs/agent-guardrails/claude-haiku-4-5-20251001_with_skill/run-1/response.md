The problem is that you're trying to use **instructions** to enforce rules, and instructions degrade—this is exactly the failure mode your project's CLAUDE.md describes:

> **If your change relies on someone remembering something, it is not finished.**

Caps and repetition are training, and training doesn't hold. Caps just means the failure will be spectacular when it happens. Your 1-in-10 slip rate is actually the normal degradation curve for even well-intentioned instruction-following in long sessions or across tool chains.

To fix this, convert those rules to **devices**—automated checks that make violations **mechanically impossible** before they reach git:

### For "never edit files in src/generated/"

**Git hook (pre-commit):**
```bash
# .git/hooks/pre-commit
if git diff --cached --name-only | grep -q '^src/generated/'; then
  echo "❌ Generated files are read-only. Revert changes to src/generated/"
  exit 1
fi
```

### For "never force push"

**Git hook (pre-push):**
```bash
# .git/hooks/pre-push
# Reject force-push attempts entirely
if [[ "$@" == *"--force"* ]] || [[ "$@" == *"-f"* ]]; then
  echo "❌ Force push is disabled. Resolve conflicts with rebase/merge instead."
  exit 1
fi
```

**Install both with:**
```bash
mkdir -p .git/hooks
# paste the hook code above into the files
chmod +x .git/hooks/pre-commit .git/hooks/pre-push
```

The poka-yoke philosophy is: **verify the instrument before you trust it.** Before committing these hooks, deliberately break the rule on purpose and watch the hook catch it. Then you'll know it's real.

This is why every check in `.github/workflows/validate.yml` exists—not as backup to instructions, but as the actual rule. Instructions are your backup.