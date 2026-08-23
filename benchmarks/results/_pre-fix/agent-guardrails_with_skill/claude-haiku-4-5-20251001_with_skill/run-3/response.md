Your CLAUDE.md instructions are guidance, not enforced constraints — they're contextual rules that degrade during context compaction, subagent spawning, and cognitive load. That's why you're seeing ~10% violation despite caps and repetition.

**The diagnosis from earlier in this session:** Your prior conversation identified this exact issue and split it into two control layers:

1. **CLAUDE.md** (rung-0 training) — degrades under pressure
2. **settings.json deny rules** (rung-1 hard blocks) — enforced at the tool level, never violated

Right now you're only using layer 1. To actually prevent these actions, you need **settings.json deny rules** — they're a different mechanism entirely:

**For force-push:**
```json
{
  "permissions": {
    "global": {
      "deny": ["git push --force", "git push --force-with-lease"]
    }
  }
}
```

**For src/generated/ edits:**
```json
{
  "permissions": {
    "global": {
      "deny": ["edit src/generated/**", "write src/generated/**"]
    }
  }
}
```

Plus server-side: GitHub branch protection (require pull request reviews, dismiss stale on push) for force-push, and file headers + CI regeneration for src/generated/.

Would you like me to implement these deny rules in your settings.json? And do you want:
- A hard block on `--force-with-lease`, or
- A softer block that requires explicit `/force-push` approval first?