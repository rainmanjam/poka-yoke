You're running into the exact problem your project is built to solve. From your CLAUDE.md: *"If your change relies on someone remembering something, it is not finished."* Training degrades. You've done the training. Now build the device.

Two changes, both automated:

**1. Pre-commit hook** (catches it locally, friction-free)
- Runs the formatter and type-checker on staged files
- **Auto-fixes formatting** (don't reject, fix it)
- **Rejects on type errors** (requires human decision)
- Developer runs `git commit`, gets formatted code back, re-stages, commits

**2. CI check** (catches anything that slipped past)
- Blocks merge if code is unformatted or untyped
- Could auto-commit fixes to the branch (convenient) or just fail (strict)

**The key difference from your current approach:**
- No one has to *remember* to run the formatter
- No one has to *read* CONTRIBUTING.md
- No one has to *hear* standup
- The workflow itself enforces it

Skip the "add this to your mental checklist" framing entirely. Make it part of the commit machinery, where it can't be forgotten.

For the formatter especially, auto-fixing is worth it — people don't have strong opinions about whether their commas have spaces, so fixing it silently removes friction. Type annotations are stricter (that's a real decision), so blocking on those is reasonable.

This is the difference between a rule and a poka-yoke device: the device makes the failure impossible, or impossible to ignore, instead of relying on discipline.