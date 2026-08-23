The one-sentence diagnosis: **CLAUDE.md is prose, and prose is rung zero** — it's training, not enforcement, and training degrades under long contexts, compaction, and subagents that never even read the file. The ~1-in-10 failure rate isn't a wording problem; it's what "rung zero" looks like statistically. There's no `.claude/settings.json` in this repo at all, so right now nothing actually *stops* either action — Claude just usually remembers not to.

Here's the full replacement, not just the insight:

**1. Deny rules — the actual syntax, in `.claude/settings.json` (committed, so it protects everyone, not just your machine):**

```jsonc
{
  "permissions": {
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

**2. Where a pattern alone isn't enough:** `git push --force` is a clean prefix match, so the deny rule above is sufficient — Control, no hook needed. `src/generated/**` is also a clean path glob for Edit/Write. Neither of your two rules actually needs a `PreToolUse` hook; you got lucky in that both are expressible as static patterns. (If you ever wanted `--force-with-lease` allowed but bare `--force` blocked, or wanted the generated-file rule to only apply outside a specific regenerate script, that's when you'd need a hook that inspects the call.)

**3. The deny message:** default deny messages are terse. Consider adding a companion message so the agent doesn't just try `git push -f` as a workaround for a blocked `--force`:
> Blocked: force push. This can overwrite others' work on the remote. If you need to fix a mistaken push, ask the user to do it, or use `--force-with-lease` after confirming with them.

**4. Where it lives:** `.claude/settings.json`, committed to the repo — not `settings.local.json`. A rule that only exists on your machine is the same failure mode as a CLAUDE.md line: it protects only where someone remembered to set it up.

**5. Verify it actually fires — don't skip this:** run `git push --force` and an edit to a file under `src/generated/` and confirm both get denied with the message you expect, then run a normal push and a normal edit elsewhere and confirm those still work. An unverified deny rule is worse than none — a typo'd glob (e.g. forgetting the repo uses `generated/` at the root, not `src/generated/`) fails open while looking like protection.

Want me to check this repo's actual generated-file path and write the `.claude/settings.json` now?