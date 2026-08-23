Nothing's wrong with your wording — the problem is the mechanism. A line in CLAUDE.md, even in caps, even twice, is what poka-yoke calls **rung 0**: it relies on the agent remembering, and "remembering" degrades under long contexts, context compaction, and subagents that never load the file in the first place. That ~1-in-10 failure rate isn't a fluke, it's the expected failure rate for training-based enforcement — it doesn't matter how emphatically it's phrased, because the agent isn't consulting a rule at the moment it acts, it's pattern-matching on a compacted memory of one.

The fix is to move both rules off rung 0 (prose) onto rung 1 (control) — a device that denies the action before it executes, not a hope that it gets read:

**`never force push`** → a permission deny rule. This is the cleanest case: it's a fixed, matchable command string.
```jsonc
// .claude/settings.json
{
  "permissions": {
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(git push --force-with-lease:*)"  // optional — see caveat below
    ]
  }
}
```
Belt-and-suspenders: also turn on branch protection on the remote (GitHub/GitLab) so it's blocked server-side too, independent of what's running locally.

**`never edit files in src/generated/`** → also a deny rule, since it's a fixed path:
```jsonc
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```
Pair it with a `// AUTO-GENERATED — DO NOT EDIT` header at the top of each generated file — belt-and-suspenders again, and it also warns *humans* opening the file, which CLAUDE.md never does.

Two things worth deciding before I write this:
1. **`--force-with-lease`** is safer than a bare `--force` (it fails if someone else pushed in between), so some teams allow it. Do you want it denied outright, or allowed?
2. Deny rules throw a hard error with a message the agent reads — worth writing something like *"Blocked: force-push is disabled on this repo. If you need to rewrite remote history, ask the user to run it themselves."* so a denial doesn't just trigger a creative workaround attempt.

Want me to write `.claude/settings.json` with these two rules once you've picked an answer on force-with-lease?