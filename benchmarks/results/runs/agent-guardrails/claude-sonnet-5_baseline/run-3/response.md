Nothing's wrong with your wording — the problem is the mechanism. CLAUDE.md text is a prompt, not a constraint: it gets read probabilistically, and it's exactly the kind of thing this repo's own CLAUDE.md warns against — "If your change relies on someone remembering something, it is not finished." A model is "remembering" your rule the same way a person would, and it's vulnerable to the same failure modes: long-context dilution, summarization/compaction dropping it, and subagents that never got the parent's CLAUDE.md in their prompt at all. CAPS and repetition raise the odds; they don't make it a device.

The fix, per this repo's own framework, is to turn both rules into something that can't be bypassed rather than something that has to be recalled:

1. **`src/generated/` edits** → deny it at the permissions layer in `.claude/settings.json` (`permissions.deny: ["Edit(src/generated/**)", "Write(src/generated/**)"]`). The tool call fails before it executes — no model judgment involved.
2. **Force-push** → a `PreToolUse` hook on `Bash` that regex-matches `git push.*(--force|-f\b)` and exits nonzero to block it, independent of what the model intends to type.

Want me to set both of those up? There's no `.claude/settings.json` in this repo yet, so it'd be a new file — I'd use the `update-config` skill for this since it's exactly this kind of change.