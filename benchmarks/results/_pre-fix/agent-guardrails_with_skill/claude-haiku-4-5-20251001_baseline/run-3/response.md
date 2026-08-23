The problem isn't your instructions—it's that **CLAUDE.md is a training-level guidance, not a technical control**. It degrades under the exact conditions you're hitting: context compaction, subagent spawning, and reasoning pressure.

When context gets compressed mid-session, your CLAUDE.md can get trimmed. When I spawn subagents, they inherit routing rules but not necessarily the full breadth of edge-case directives. Under time pressure or complex multi-step reasoning, I may miss a nuance I'd catch in a clear context.

**The fix: layer in technical controls** that the *harness* enforces, not the model's judgment:

1. **`settings.json` deny rules** — block `git push --force` and `git push --force-with-lease` entirely at the CLI level, before the model even attempts it.
2. **GitHub branch protection** — server-side force-push block on `main`.
3. **File header guards** — `src/generated/` files get a comment header that warns on any edit, plus CI regeneration that fails if they were modified by hand.
4. **CI gates** — regenerate `src/generated/` on every test run; fail the build if content diverges from the source.

Would you like me to use the **update-config** skill to add the deny rules to your settings? That alone will eliminate the force-push violations entirely.

For `src/generated/`, I'd recommend: file headers + a quick CI check that regenerates and diffs. That prevents the "oops I edited this by hand" case.