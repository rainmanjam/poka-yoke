You’re using reminders to solve a constraint problem. Caps and repetition can increase salience a little, but neither creates enforcement—so occasional failures are expected.

Make the forbidden action mechanically hard or immediately detectable:

- **Generated files:** add a pre-commit/CI check that fails if `src/generated/**` changes, unless an explicit, narrowly scoped regeneration command or approval marker is present. Ideally make regeneration overwrite the directory from its source of truth.
- **Force-push:** protect the remote branch in GitHub/GitLab: disallow force pushes, require PRs, and restrict who can bypass protections. A local Git hook can add a helpful early stop, but server-side protection is the actual device.
- **Agent workflow:** give Claude safe commands it can use—e.g. “edit the generator inputs, then run `make generate`”—rather than only naming forbidden paths.

The instruction itself should be short and operational, but treat it as context, not a guardrail:

> Generated output is read-only. Edit its source, then run `…`; CI rejects direct changes under `src/generated/`.

The real fix is: ensure the bad state can’t merge or reach the protected branch.