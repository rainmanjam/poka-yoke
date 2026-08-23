# Contributing to poka-yoke: guidance for agents and people

This repository argues that instructions degrade and devices do not. It has to hold itself
to that, so read this before changing anything here.

## The one rule that governs the rest

**If your change relies on someone remembering something, it is not finished.**

A comment, a checklist item, a line in this file: those are training. Training degrades.
When you fix something here, ask what device would have caught it, and add that too. Every
check under `.github/workflows/validate.yml` exists because something drifted silently first.

## Verify the instrument before you trust it

The recurring failure in this project is not broken code. It is **a check that cannot fail**. Every one of these looked
like a passing test:

- The detector reported `{"count": 0}` for a clean scan and for scanning nothing at all.
- The description optimizer failed its own positive control, so its numbers were void.
- A thumbnail scorer returned byte-identical floats for different images.
- A beat checker watched opacity while the thing it measured was still moving.

So when you add a check, prove it fails. Break the thing on purpose, watch the check catch
it, put it back. A check that has never once gone red is a rumour, not a device.

Two shapes recur often enough to name. **A probe keyed to prose stops probing when the prose
changes.** A README figure check that matched `**N% → M%**` silently verified nothing after a
rewrite moved the numbers out of bold, and passed while checking zero claims. Assert that the
probe found something before asserting the something is correct. **And absent data does not
raise.** A failed run leaves an empty directory, a missing grading just shrinks a cell, and a
narrowed aggregate simply reports fewer columns. Each looks like the shape of the matrix rather
than like an error, so make missing input fail loudly instead of averaging what remains.

When you touch the benchmark: aggregate over the **full** matrix before quoting anything.
Narrowing `--models` or `--scenarios` rewrites the summary as though the omitted cells never
existed. The harness prints `::warning:: this aggregate is NARROWER than the one it replaces`
when that happens. Do not pipe it through `tail`, which is how it went unread three times in
one session.

`tests/test_detector.py` shows the shape a rule's tests take: a case that must match **and**
a near-miss that must not. The file is not there yet: 14 of the 20 hazard shapes have the
matching case and 6 have the near-miss, so supplying whichever half is missing is part of
touching a rule. The near-misses are what keep precision high enough that people don't learn
to ignore the tool.

## Skills

Skills are behaviour-shaping content, not prose. Two constraints are enforced in CI:

- **Descriptions compete for a truncated budget.** Claude Code shortens skill descriptions
  to fit a listing that contains every installed skill. On a machine with hundreds of them,
  a long description loses its tail, and trigger phrases at the end are exactly what gets
  cut. Put concrete domain nouns and quoted user phrasing early. The exact cut-off is not
  published and nothing here measures it, so treat the front of the description as the part
  that survives and do not rely on a specific number.
  `tests/test_skill_listing.py` enforces the budget.
- **A skill body over 500 lines belongs in `references/`.** Progressive disclosure is the
  point: metadata always loads, the body loads on trigger, references load on demand.

Changing skill content without evidence is not an improvement, it is a coin flip. Use
`benchmarks/run.py` and report before/after.

## Paths must not assume Claude Code

The skills ship to 19 runtimes. Two rules make that possible, and `tests/test_portability.py`
enforces both:

1. **No runtime-specific path variables.** Reference bundled files relative to the SKILL.md
   that reads them (`../../references/hazard-catalog.md`), never `${CLAUDE_PLUGIN_ROOT}`.
2. **No absolute or runtime-specific script paths.** Invoke bundled scripts relative to the
   SKILL.md that names them (`../../scripts/detect_hazards.py`). An agent that just read the
   skill knows where it is; it does not know what `${CLAUDE_PLUGIN_ROOT}` means.

Runtime-specific material (hook templates, settings snippets) lives under
`assets/devices/<runtime>/` and is referenced behind a capability clause, never assumed.

## Pull requests

- One problem per PR. Describe the problem you hit, not just the diff.
- If you changed a check, show it failing before your fix and passing after.
- If you are an agent: show your human partner the complete diff first, and say in the PR
  which model and harness produced it. That is not a formality. Work reasoned from docs is
  weighed differently from work grounded in a real session.
- Do not add dependencies. The detector is standard library only on purpose: it runs in CI,
  in pre-commit, and inside agent sessions on machines we do not control.

## Layout

```
plugins/poka-yoke/
  skills/<name>/SKILL.md    behaviour, one per mode
  references/               loaded on demand, not into every session
  scripts/                  the executable devices
  assets/devices/           templates you choose to apply; read before installing
benchmarks/                 A/B measurement against a no-skill baseline
tests/                      the devices that guard the devices
```
