# Review — skills and benchmark results — 2026-08-25

**Mode**: the benchmark half is `data` (failure here is a silently wrong number, not a crash);
the skills half applies the method directly, since no specialist mode covers "is this
behaviour-shaping content any good".

**Verdict**: the project's headline figure does not reconcile with the data in this
repository, and it is the one figure the verification test deliberately skips.

---

## 1. The headline claim cannot be reproduced from the stored gradings

**Where**: `README.md:10-11`, `README.md:81`, and every downstream copy — the OpenAI bundle,
the SKILL.md in github/awesome-copilot#2792, the Reddit posts, the Show HN submission.

**The claim**: *"Unprompted, models close a design by naming what it forecloses **42%** of the
time. With these skills, **81%**, measured across 80 graded verdicts and six model families."*

**What the gradings actually contain.** The assertion family is four assertions across four
scenarios (`design`, `build-endpoint`, `build-form`, `build-agent-feature`). All 144 runs in
those cells have a `grading.json`; none are missing.

| Computation | Baseline | With skill | Verdicts |
|---|---|---|---|
| Whole family, all models | **50%** | 82% | 144 |
| Whole family, `CURRENT` six models (the test's own filter) | **45%** | 80% | 132 |
| The only subset totalling 80 verdicts (`build-*`, excluding `design`) | **25%** | 75% | 80 |
| **README** | **42%** | **81%** | **80** |

An exhaustive search over every subset of scenarios finds **no combination that yields
42% → 81%**. The verdict count of 80 matches the three `build-*` scenarios exactly, but those
give 25% → 75%.

**The data has not moved underneath the figure.** `benchmarks/results/runs` and
`benchmark.json` were last written in `3eb21d4` (2026-08-23). The 42% figure entered the
README in `c597941`, which is later. It was written against exactly this data.

**Mistake**: publish a headline figure and, separately, write the test that verifies the
table it sits in — with that row excluded.

**Consequence**: the most-quoted number in the project is unverifiable and does not match its
own evidence. Silent, and it has already been repeated into four external venues.

**Today**: **None.** `test_trade_table_figures_come_from_the_gradings` checks four rows and
skips this one:

```python
if key is None:
    continue    # "Names what the design makes impossible" is a
                # family, covered by its own aggregate elsewhere
```

That "elsewhere" does not exist — grep finds no other test referencing this family.

**Device**: extend the existing test to cover the family row: sum the four assertions across
both arms, round the same way, and require the README's two numbers to match. Then either
correct the README to the recomputed figures or, if 42/81 came from a defensible narrower
population, state that population in the sentence — "across the three build scenarios" is a
true sentence; "across 80 graded verdicts" without saying which is not.
→ **Control**, and it costs about fifteen lines in a test that already exists.

**Do this before the awesome-copilot PR is reviewed**, since the same sentence is in it.

---

## 2. The effect is concentrated, and the family average hides it

Per scenario, on the same assertion family:

| Scenario | Baseline | With skill |
|---|---|---|
| `design` | **81%** | 91% |
| `build-agent-feature` | 33% | 83% |
| `build-form` | 29% | 64% |
| `build-endpoint` | 14% | 79% |

`design` — the scenario most people will assume the headline is about — already passes 81%
of the time **with no skill loaded**. The skills add 10 points there. The large gains are in
the three `build-*` scenarios, where a model is writing a feature and not being asked to
design an interface.

That is a more interesting and more defensible claim than the average: *the skills matter most
when nobody asked for a design review.* The current framing averages a 10-point effect
together with a 65-point one and reports the mean, which understates the good case and
overstates the easy one.

**Device**: publish the per-scenario table instead of the family mean. → **Detection**; it is
a positioning change, not a mechanism.

---

## 3. The control arms have never been run, and `--check` is green anyway

`benchmark.json` contains **77 baseline cells and 77 with_skill cells. Zero `with_placebo`,
zero `with_defensive`.** The arms exist on disk and are locked:

| Arm | Routes | Files | Words |
|---|---|---|---|
| `with_skill` | 10/10 | 19 | 24,940 |
| `with_placebo` | 5/10 | 6 | 5,596 |
| `with_defensive` | **2/10** | 3 | 3,239 |

`preregister_arms.py --check` passes on arms that are one-fifth authored, because it verifies
that hashes have not *changed*, not that the arms are *runnable*. A sweep run today would
route half the placebo scenarios to a missing sub-skill and measure the absence of
instructions rather than the presence of a different methodology.

The README is honest that the baseline is "no methodology". The hazard is that the arms look
ready — they have a lock file and a passing check — and they are not.

**Device**: `cmd_check` requires every route named by an arm's router to resolve to a
`SKILL.md`, and requires route parity with `with_skill` before accepting the lock.
→ **Control.** This is finding #4 of the swarm sweep, unfixed.

---

## 4. Statistical resolution is not carried alongside the numbers

154 cells, run counts distributed `n=1: 4 · n=2: 23 · n=3: 87 · n=7: 40`. Median **3**.

`by_model` records **no `n` at all**, so the six-row summary — the most-read table — cannot be
weighted or discounted by a reader. A 3-run cell and a 7-run cell are visually identical.

**Device**: emit `n` into `by_model` and print it beside every published percentage.
→ **Detection.** Control would mean refusing to publish a cell below a minimum n, which is a
policy decision rather than a bug fix.

---

## 5. The skills themselves are in good shape, with one gap

| Measure | Result |
|---|---|
| Body length | 127–184 lines, all well under the 500-line rule |
| Description length | 325–436 chars, all within the truncation budget |
| Benchmark coverage | 10 of 11 skills have a scenario |

The exception is **`poka-yoke`, the router** — the skill loaded when someone types
`/poka-yoke` with no mode, and the one that decides which specialist to hand off to. It has
no benchmark scenario. Routing *accuracy* is measured separately by `trigger_eval.py`, but
that measures whether descriptions carry the words users say; it does not measure whether the
router's own body produces better output when no specialist fits.

Given that this is the default entry point, it is the skill whose content changes are least
evidenced — in a repository whose contributing guide says changing skill content without
evidence is a coin flip.

**Device**: add a scenario exercising a subject none of the ten modes covers — the guide's own
examples are a runbook, a release checklist, a spreadsheet — so the router is measured doing
the thing it claims to do. → **Detection.**

---

## What I did not review

Skill prose quality, wording and structure. Those are style judgements, and this method is
explicit that a finding which cannot name a wrong action someone could take is not a finding.
