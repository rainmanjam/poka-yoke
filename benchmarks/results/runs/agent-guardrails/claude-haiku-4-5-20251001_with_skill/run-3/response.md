Your instructions are being loaded, but they're probably getting buried in context noise—Claude sees them, but they don't stand out enough to reliably gate the action. A few things are working against you:

1. **Capitalization alone doesn't work.** The system reminders show that effective hard rules use structural markers: section headers like `## BLOCKED`, `## MANDATORY`, or opening with phrases like `You MUST NEVER` (strong modal, not just caps). Rules buried in prose—even in caps—blend into regular guidance.

2. **Rules need context to survive edge cases.** When you just say "never edit src/generated/", Claude might follow it 90% of the time. But the 10% where it breaks is usually when:
   - The user explicitly asked for it in a follow-up
   - It seems like the fastest path to fix something
   - The reason is unclear, so it feels like an arbitrary restriction

   If you add **Why:** (context behind the rule) and **How to apply:** (when it kicks in), Claude can judge edge cases instead of blindly applying or ignoring it.

3. **High-stakes rules need both format and placement.**  Look at your own `context-mode` section in CLAUDE.md:
   ```markdown
   ## BLOCKED commands — do NOT attempt these
   
   ### curl / wget — BLOCKED
   Any Bash command containing `curl` or `wget` is intercepted...
   ```
   This works because it's isolated, has a clear header, states the rule, and explains what to do instead.

**Try this structure:**

```markdown
## MANDATORY — never edit src/generated/

These files are generated from templates. Editing them directly is lost on the next build.

**Rule:** Do not modify any file under `src/generated/` for any reason.

**Why:** Generated files are rebuilt from source. A direct edit looks like a fix but evaporates silently on the next build cycle, breaking the build and confusing future readers.

**How to apply:** If something in `src/generated/` needs to change, find and modify the **template or script** that generates it (`src/templates/` or `scripts/generate.js`). If you don't know where it comes from, ask before touching it.

**Exception:** None. If you need to patch a generated file to unblock work, do it, but file an issue and document exactly which line and why—so the template gets fixed.
```

Same for force push:

```markdown
## MANDATORY — never force push

**Rule:** Do not run `git push --force`, `git push -f`, or `git push --force-with-lease` unless you have explicit, in-advance permission from the team lead.

**Why:** Force push can discard teammates' work invisibly. It breaks shared branches and makes history unreliable.

**How to apply:** If you need to rewrite history, create a new branch from your current state, make the changes, and open a PR for review instead. If you hit a truly blocked state (e.g., a broken main branch that needs emergency surgery), ask first.
```

The structure (rule + why + how to apply) gives you judgment calls in edge cases, and the section header makes it visually distinct so it doesn't fade into the noise.