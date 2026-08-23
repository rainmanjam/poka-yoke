The answer is in your own CLAUDE.md: **text is training, and training degrades.** Caps and repetition slow the degradation but don't stop it.

What you need isn't a better instruction—it's a *device*. The hooks need to live in `.git/hooks/` or a `.husky/` config so the harness (git itself) prevents the action, not Claude's memory.

**Two hook scripts:**

1. **.git/hooks/pre-commit** — blocks staged edits to `src/generated/`:
   ```bash
   #!/bin/sh
   if git diff --cached --name-only | grep -q '^src/generated/'; then
     echo "❌ Error: src/generated/ is read-only"
     exit 1
   fi
   ```

2. **.git/hooks/pre-push** — blocks force-push:
   ```bash
   #!/bin/sh
   if [[ "$*" == *"--force"* || "$*" == *"-f"* ]]; then
     echo "❌ Error: force push is blocked"
     exit 1
   fi
   ```

Make them executable: `chmod +x .git/hooks/pre-commit .git/hooks/pre-push`

**If you want this in version control** (so new clones get the hooks), use [husky](https://typicode.github.io/husky/) — it auto-installs hooks on `npm install`.

Once the device is in place, the 10% failure vanishes because git itself rejects the action. Claude can't bypass it—nobody can. That's why devices matter more than instructions.