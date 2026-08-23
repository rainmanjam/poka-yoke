## The problem you hit

Describe what went wrong, not just what you changed. A diff explains the how; this explains
whether the change is the right one.

## The device

If your change relies on someone remembering something, it is not finished. What would have
caught this automatically, and did you add it?

- [ ] I added a check, or one already existed and I said which
- [ ] **I broke the thing on purpose and watched the check go red**, then put it back
- [ ] Not applicable, and here is why:

## If you touched a detector rule

- [ ] A case that must match
- [ ] A near-miss that must not

## If you touched a skill

Skill content changes without evidence are a coin flip. `benchmarks/run.py` measures them.

- [ ] I ran the benchmark and pasted before/after
- [ ] The change cannot affect behaviour (formatting, a typo) and I say so below

## If you touched anything carrying a `poka-yoke:` marker

- [ ] I regenerated the device registry in this same commit

## Provenance

If an agent wrote any of this, say which model and harness. That is not a formality: work
reasoned from documentation is weighed differently from work grounded in a real session.
