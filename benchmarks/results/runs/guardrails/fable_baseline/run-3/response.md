Stop trying to get people to follow it. You've already run the experiment: a written rule, a pinned message, and two verbal reminders got ~50% compliance, and that number will decay, not improve. The problem isn't the team's memory or buy-in — it's that the rule lives in a place that can only be *remembered*, and remembering is the weakest enforcement mechanism there is. Your own repo's CLAUDE.md puts it bluntly: *if your change relies on someone remembering something, it is not finished.*

Move each rule from training into a device, and pick the layer by how much friction you want:

**Make it automatic (best for the formatter).** The formatter is a mechanical transform with no judgment involved, so nobody should be running it at all:
- Editor format-on-save, committed as a workspace settings file so it's on by default for everyone who opens the repo.
- A pre-commit hook (via `pre-commit`, `husky`/`lint-staged`, or whatever fits your stack) that *reformats and re-stages* the staged files rather than rejecting the commit. The commit simply comes out formatted.
- A bot that pushes a "chore: format" commit onto any PR that drifts. Zero human cost.

**Make it impossible to merge (the backstop for both).** A required CI check that runs `<formatter> --check` and your type checker in strict mode on changed files, wired into branch protection so the merge button is disabled while it's red. This is the one that actually moves the number, because it doesn't care who remembered. The local hooks just make it cheap to stay green.

**Make the type rule gradual, not aspirational.** "Annotate new code" is hard to check because "new" is fuzzy. Two workable shapes: a ratchet (a script records the current untyped-function count and fails CI if it goes *up*), or strict mode enabled per-directory/per-file with an allowlist of legacy paths that only shrinks. Either way the device decides what counts as new, not a reviewer.

**Verify the device before you trust it.** Open a deliberately unformatted, untyped PR and watch it go red. A check nobody has seen fail is a rumour.

One thing to reframe with the team: this isn't a judgment on them. Half the PRs came in wrong because half the people have different editor setups, contexts, and Friday-afternoon attention spans — that's normal human variance, and the retro agreement asked people to overcome it by willpower. Replace the ask with a machine and the retro item closes for good. Remove the CONTRIBUTING.md paragraph once the check exists, or shrink it to "run `make setup`; the hooks handle the rest."

If you want, I can look at what stack this applies to and wire up the hook + CI check.