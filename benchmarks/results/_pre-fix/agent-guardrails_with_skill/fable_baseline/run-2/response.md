Nothing wrong with the wording. Caps and repetition don't help because the failure isn't comprehension — it's that a CLAUDE.md line is a *training-level* control (rung 0 on the poka-yoke ladder: "tell the worker to be careful"), and those degrade exactly the way you're seeing:

- **Context compaction** — after a long session the instruction gets summarized or drops out of the active window.
- **Subagents** — spawned agents get a fresh context; your CLAUDE.md may or may not be in it.
- **Task pressure** — when the model is focused on "make CI green" and the generated file is the thing failing, the local goal wins 1 in 10.

Any control that lives in the model's attention will fail at roughly that rate. The fix is to move both rules out of prose and into the harness, where the model *can't* do the thing.

**Force-push**
1. `settings.json` deny rule: `"deny": ["Bash(git push --force*)", "Bash(git push -f*)"]` — the tool call is refused before it runs.
2. GitHub branch protection on `main` (block force pushes) — catches it even if the deny is bypassed, the model rewrites the command, or someone runs it outside Claude.

**`src/generated/`**
1. `settings.json` deny: `"deny": ["Edit(src/generated/**)", "Write(src/generated/**)"]`.
2. A `// @generated — DO NOT EDIT, regenerate with npm run gen` header in each file (helps the model self-correct when it does read the file).
3. CI step that regenerates and `git diff --exit-code` — hand-edits can't merge even if they slip through.

Keep the CLAUDE.md lines, but shorten them and point at the *why* plus the correct action ("regenerate with `npm run gen`"; "use `--force-with-lease` on feature branches only" — or forbid that too). The model follows a sentence that tells it what to do instead far better than one that only says NO.

One decision only you can make: do you want `git push --force-with-lease` on non-main branches allowed, or blocked outright? That determines whether the deny pattern is `--force*` (blocks both) or needs to be two separate entries. Tell me and I'll write the `settings.json` changes and the CI check.