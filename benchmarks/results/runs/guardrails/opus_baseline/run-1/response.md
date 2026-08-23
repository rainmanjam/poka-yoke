You've done the three things that don't work, and you did them thoroughly. That's useful data: the problem isn't that the message failed to arrive.

**Separate the three:**

- **Defect:** unformatted, untyped code lands on main.
- **Mistake:** someone commits without running the formatter.
- **Hazard:** *the repository accepts unformatted, untyped code.* Nothing between a developer's editor and main rejects it.

Run the whys and you stop at "they forgot." Keep going: why is forgetting possible? Because compliance depends on a human recalling a rule at the moment of commit, every commit, forever. That's a training-rate problem, and human training rates plateau around 90% on a good day — you're seeing 50% because the rule competes with everything else in a working memory. Two more standup mentions gets you to maybe 60%.

**The devices, by rung:**

| Rung | Device |
|---|---|
| **Control** | CI job that fails the PR on `--check` diff. Branch protection makes it non-mergeable. Formatting becomes physically impossible to skip. |
| **Control** | Type checker in CI with a **ratchet**: current error count is committed to a file, CI fails if the count goes up. New code must be typed; nobody has to boil the ocean. |
| **Warning** | Pre-commit hook (`pre-commit`, `husky`). Catches it earlier and more kindly, but it's bypassable with `--no-verify` and only installed on machines where someone ran the install step. |
| **Detection** | A bot that comments on unformatted PRs. Better than nothing, still relies on someone acting. |
| **Zero** | CONTRIBUTING.md, the pinned Slack message, the standup mentions. |

The highest-leverage version removes the task entirely rather than enforcing it: have CI **auto-format and push the fix back** to the PR branch, or use a merge-queue formatting step. Then "run the formatter before committing" stops being a rule anyone has to remember — it's just something that happens. Format-on-save in a committed editor config (`.vscode/settings.json`, `.editorconfig`) does the same work upstream.

`★ Insight ─────────────────────────────────────`
The ratchet pattern is why type adoption succeeds or stalls. "Add annotations to new code" is unenforceable because CI can't tell new code from old — but it *can* count errors and refuse an increase. The constraint is expressible; the instruction wasn't.
`─────────────────────────────────────────────────`

One honest caveat: a CI gate converts a social problem into a red build. If the check is slow or noisy, people learn to ignore or bypass it, and you've spent trust for nothing. Make it fast, make it auto-fix where it can, and turn it on for new commits only.

Two things I need before I can write the actual config: **what's the stack** (Python/mypy? TS?), and **do you want CI to auto-fix and push, or fail and make the author fix it?** The second is a real team call — auto-push is frictionless but rewrites people's branches under them.