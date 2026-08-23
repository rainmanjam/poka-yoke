Your project literally has the answer to this in CLAUDE.md: **"If your change relies on someone remembering something, it is not finished."**

Training (docs, Slack, standups) degrades. What you need are *devices* — automated checks that prevent the unformatted/untyped code from being submitted in the first place.

Three layers:

**1. Pre-commit hook** (catches it before the branch exists)
- Runs formatter + type checker on staged files
- Either auto-fixes (formatter) or blocks the commit (type checker)
- Most developers never see the CI because it's caught locally

**2. CI block in `.github/workflows/validate.yml`** (catches what slipped through)
- Formats/lints on the PR, fails if changes are needed
- Makes it impossible to merge without fixing

**3. (Optional) Auto-fix commit in CI** (for formatter-only)
- If someone pushes unformatted code, the CI commits the formatting automatically
- Removes the friction of "go fix it and re-push"

**Why this works:** It's not about being stricter. It's about removing the decision point. Right now, developers have to *remember* to run the formatter—and memory is the weakest part of any system. Pre-commit hooks make it impossible to forget; the tool runs whether you think about it or not.

The team agreed on the standard. They didn't fail because they're careless—they failed because you asked them to *remember*. Move that burden to a device instead.

Do you want me to help you set up pre-commit hooks and/or add the CI checks? I can write the config and show you what it catches before you commit it.