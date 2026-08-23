I see the issue — and it's not your instructions. The rules you're describing aren't in your current CLAUDE.md, which suggests either they haven't been added yet or they're in a separate file. But more importantly, **text instructions alone can't reliably prevent 10% slip-through.**

Here's why caps and repetition don't land reliably:

**Context compaction** — When long conversations compress, CLAUDE.md is re-injected but rule reinforcement degrades. **Subagents** — spawned agents inherit CLAUDE.md as training guidance, not hard constraints. **Reasoning under pressure** — token/context stress can cause shortcuts that override written rules.

Text in CLAUDE.md is a *training signal*, not an enforcement gate. For critical rules like "never force-push" and "never edit src/generated/", you need **server-side controls** that work regardless of context state:

**For force-push:**
- GitHub branch protection (admin-enforced, can't bypass via tool)
- `.claude/settings.json` deny rule (harness-level block before the git command runs)

**For src/generated/:**
- `.claude/settings.json` deny patterns (blocks file edits before they happen)
- CI regeneration (edits are always reverted, so slip-through attempts fail silently)
- Pre-commit hook (rejects commits containing edits)

**Fix:** Use the `/update-config` skill to add deny rules to settings.json. This moves these from "Claude should remember" to "Claude cannot even attempt it."

```
DENY: git push --force*, git push --force-with-lease
PATTERN_DENY: src/generated/**
```

Once those are in place, the ~10% slip-through becomes 0% because the harness blocks the operation before Claude's reasoning even lands.

Would you like me to set those up now?