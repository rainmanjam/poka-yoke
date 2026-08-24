# What the benchmark cannot currently answer

Ranked by which published claim each gap threatens. Measured against the committed harness and
`benchmarks/results/benchmark.json` on 2026-08-24.

---

## 1. There is no active control, so the headline claim is under-determined

**The gap.** Two arms exist: `baseline` and `with_skill`. Nothing separates *"these skills work"*
from *"any structured methodology occupying that much context works"*. Every published delta is
consistent with both.

**Why it is first.** It is the second question a sceptic asks, it invalidates the headline rather
than qualifying it, and it is the cheapest of the big fixes.

**Design.** A third arm, `with_placebo`: a methodology skill of comparable length and structure
that is plausible but does not encode the poka-yoke method. Generic clean-code advice matched on
token count is the obvious candidate. Report `with_skill − with_placebo` alongside the current
`with_skill − baseline`. If the two deltas are close, the honest conclusion is that structure in
context helps and the specific method is unproven.

**Cost.** +50% runs. Grading is unchanged.

## 2. Every measurement is at turn one, with an empty context

**The gap.** Runs go through `claude -p`, `agy -p` and `codex exec --ephemeral`. Single turn, fresh
context, 13 prompts of 27 to 102 words, and no multi-turn field in the scenario schema.

**Why it matters.** The project's own thesis is that instructions degrade and devices do not. A
skill is instructions. The thesis therefore predicts decay with context depth, and the benchmark
measures the one point where decay is zero. The result is consistent with the thesis and silent on
its sharpest consequence.

**Design.** Same scenarios, same grader, target prompt injected at turn 1, 10 and 30 of a session
padded with unrelated but realistic work. Report pass rate by depth.

**The hard part is the padding, not the runs.** Padding chosen for convenience will produce
whatever answer the padding implies. It needs to be pre-registered and fixed before any grading.

**Cost.** ~3x runs plus padding tokens.

## 3. A quarter of the cells cannot support a per-cell claim

**Measured distribution of runs per cell** (154 cells, 77 pairs x 2 arms):

| n | cells |
|---:|---:|
| 1 | 4 |
| 2 | 23 |
| 3 | 87 |
| 7 | 40 |

**27 cells rest on one or two runs.** The two regressions quoted most often, Haiku on
`build-agent-feature` at -31.2 pp and on `build-endpoint` at -11.1 pp, are both n=2. Four cells are
still n=1 despite an earlier backfill, so the caveat in the docs is understated.

**Two honest options.** Raise every cell to n>=5, or stop quoting individual cells and report only
the per-model aggregates that n=7 supports. Doing neither is the current state.

## 4. The build scenarios are graded on prose, not on behaviour

**The gap.** All 13 scenarios are graded by an LLM reading the response text. For `build-endpoint`,
`build-form` and `build-agent-feature` the model emits code, and "described the right thing" is
being used as a proxy for "produced code that behaves correctly".

**Design.** For those three, execute the produced code against a fixed test suite the model never
sees, and score pass/fail. That replaces a judgement with a measurement for the three scenarios
where it is possible, and makes the LLM-grader concern irrelevant for 3 of 13.

## 5. The grader has never been validated against a human

**The gap.** One grader model, one pass per cell. It is blind, batched, and scored against
assertions written before the runs, with prompt and checklist hashes stored. All of that controls
*bias*. None of it establishes *accuracy*.

**Design.** Hand-label a stratified sample of 50 gradings, report agreement, and publish the
confusion matrix. If agreement is poor, every number downstream is noise and that needs to be known
before anything else on this list is worth doing. Cheap, and it gates the credibility of the rest.

**Second grader.** Running a different model as a second grader on the same sample gives an
inter-rater figure for roughly the same cost, and disagreement localises which assertions are
ambiguous.

## 6. Raw percentage points are the wrong headline given the headroom effect

**The gap.** Gain correlates with baseline headroom at r = -0.59 across 77 cells. Codex at +16.8
and Opus at +3.6 started at 74.2% and 92.7% respectively, so the ranking partly measures how weak
each baseline was.

**Design.** Lead with normalised gain, the fraction of available headroom closed, and keep raw
points as the secondary column. `docs/benchmark-comparison.md` already computes this; the README
headline does not use it.

## 7. Housekeeping that affects interpretation

- `benchmarks/results/runs/` still contains `claude-opus-4-5` and `claude-sonnet-4-5-20250929` directories that are not in the current aggregate. Stale data adjacent to live data is how the wrong cell gets counted later.
- `agy` covers 12 of 13 scenarios (`audit` is not runnable in plan mode). Its column is not comparable to the others without saying so at the point the number appears.
- Codex and agy both ran read-only. Their columns describe reasoning tasks and say nothing about write-heavy work.

---

## Order of work

1. **Grader validation** (#5) first, because it gates whether anything else is worth measuring.
2. **Active control** (#4 in cost, #1 in value), because it is what the headline claim rests on.
3. **Power** (#3), which is mostly compute rather than design.
4. **Session depth** (#2), the most interesting and the most expensive to do honestly.
5. Execution grading, headline change, housekeeping.

The first two change what can be claimed. The rest change how confidently.
