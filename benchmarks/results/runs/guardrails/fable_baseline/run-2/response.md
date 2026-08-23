Stop trying to get people to follow it. Two weeks of half-compliance after a retro agreement, a CONTRIBUTING.md entry, a Slack pin, and two standup mentions isn't a people problem — it's the expected decay curve of an instruction. Every channel you've used so far relies on someone remembering at the moment they type `git commit`. The fix is to make the unformatted/untyped PR *unable to exist*, so nobody has to remember anything.

In order of leverage:

**1. Make CI the gate, not the reminder (do this first, today).**
Add a CI job that runs `<formatter> --check` and the type checker, then mark it a *required status check* in branch protection. Now an unformatted PR physically cannot merge. Nobody has to notice, nag, or review for it. This is the only step that actually closes the gap; everything below just makes it less annoying.

**2. Make compliance the path of least resistance.**
A required check that fails is friction; friction breeds resentment and "skip CI" hacks. So pair it with:
- A pre-commit hook (via `pre-commit`, `husky`, `lefthook`, whatever fits your stack) that *runs the formatter*, not just checks it. The commit comes out formatted without the author doing anything.
- Make the hook install itself — wire `pre-commit install` into `make setup` / `npm postinstall` / the dev-container, so a fresh clone has it without anyone reading a doc.
- Commit editor config (`.vscode/settings.json`, `.editorconfig`) enabling format-on-save. Most people will never hit the hook because the editor already did it.

**3. Typing needs a ratchet, not a rule.**
"Add annotations to new code" is unenforceable as stated — no tool knows what's "new." Pick a mechanical definition: run the type checker in strict mode with a baseline file of existing errors (mypy `--baseline`-style tooling, pyright's `baseline`, or a counted-errors script) and fail CI if the count *rises*. That converts a judgment call into a number that can only go down.

**4. Then delete the instruction.**
Once the device exists, shrink the CONTRIBUTING.md paragraph to "formatting and types are enforced in CI; run `make setup` to get the hooks." Prose that duplicates a check is just another thing to drift.

**Verify the device before trusting it.** Push a deliberately unformatted branch and watch the check go red. A check that's never failed is a rumour — and formatter checks in particular are notorious for silently passing because they were pointed at the wrong directory.

One honest caveat: the first week after you flip the required check on, a handful of in-flight PRs will go red and people will grumble. Auto-fixing (step 2) and a one-time "format the whole repo" commit (add its SHA to `.git-blame-ignore-revs`) take most of that sting out.

If you want, point me at the repo and stack and I'll wire up the CI check, the self-installing hook, and the type-error ratchet.