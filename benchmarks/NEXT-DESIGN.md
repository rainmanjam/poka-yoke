# What to run next, and why the current matrix cannot answer the question

The question is whether the skills help or hurt. The published matrix cannot settle it, for
three separate reasons, and one of them means a headline currently being repeated is wrong.

---

## 1. No per-cell claim in the published benchmark is supportable

Runs needed per cell to call an effect real at alpha .05, power .80:

| baseline | effect | runs needed per cell |
|---:|---:|---:|
| 80% | +10 pp | 199 |
| 80% | +20 pp | 35 |
| 60% | +30 pp | 32 |

Runs actually present: **4 cells at n=1, 23 at n=2, 87 at n=3, 40 at n=7.**

The Haiku `build-agent-feature` regression of -31.2 pp, quoted in the README, in the video
script and in every Reddit draft, sits at **n=2 and needs n>=39** before it can be called
anything. The same holds for every other individual cell, in both directions.

**What survives:** the per-model aggregates. Those pool 13 paired scenarios and already carry
confidence intervals, and those intervals exclude zero. Per-model claims are fine. Per-cell
claims are not, and the two have been presented with equal confidence.

## 2. The regressions are noise, and their scarcity is the actual result

Simulating the null of no effect, using the real per-cell run counts and the real median of 8
assertions per run:

| | negative cells |
|---|---:|
| observed | **11 of 77** |
| expected under NO effect | **28.6** (95% range 21 to 37) |

Eleven is far **below** what pure noise produces. If the skills did nothing at all, roughly
29 cells would look like regressions.

So "11 of 77 cells got worse" is not the honest caveat it has been used as. It is a
*misleading* caveat: it implies those cells carry information they do not have, and it hides
the finding that they are remarkably few. The accurate statement is:

> Individual cells are too small to interpret. Across 77 of them, only 11 came out negative
> where noise alone would produce about 29, which is evidence the effect is consistently
> positive rather than evidence of hidden harm.

**This needs correcting in the README, the video script and the Reddit drafts before any of
them go out.** It is the same class of error as the others found this week: a plausible number
computed against the wrong reference, pointing in a direction that felt appropriately modest.

## 3. Turn one measures the ceiling

The Reddit critique, restated precisely: every run is `claude -p` / `agy -p` /
`codex exec --ephemeral`, a single turn against an empty context. The project's own thesis is
that instructions degrade and devices do not. A skill *is* instructions. The thesis therefore
predicts decay with context depth, and the benchmark measures the single point where decay is
zero.

That is the sharpest open question and the current design cannot touch it.

---

## The recommended next matrix

**Trade model breadth for design rigour.** Six models at n=2-3 answers "which vendor benefits
most", a question nobody asked, whose answer is confounded anyway: gain correlates with
baseline headroom at r = -0.59, so the model ranking is substantially a ranking of how weak
each baseline was.

| | current | proposed |
|---|---|---|
| models | 6 | **2** (Opus and Haiku: the two ends of the headroom range) |
| scenarios | 13 | **8** (drop the five with the least discriminating assertions) |
| arms | 2 | **3** (baseline, skill, placebo) |
| session depth | turn 1 | **turn 1, 10, 30** |
| runs per cell | 2-3 | **8** |
| total runs | 468 | **1,152** |

Roughly 2.5x the runs, and it answers three questions the current one cannot:

**Does it beat a control?** Without the placebo arm every delta is equally consistent with
"this method works" and "any methodology document in context works". This is load-bearing:
if the delta against placebo is near zero, the honest headline changes completely.

**Does it survive a real session?** Turn 1 versus 10 versus 30, which is the Reddit question,
and the one where the project's own thesis makes a falsifiable prediction.

**Which per-cell effects are real?** n=8 will not rescue per-cell claims (that needs ~35), but
it makes the per-model-per-depth cells solid, which is the level the conclusions should live
at anyway.

### What to defer

- **The defensive arm.** More interesting, less load-bearing. Add it once the placebo result is in; if placebo already collapses the effect, defensive is moot.
- **The other four models.** Nothing is lost: their columns can be rerun later against a design that is known to work.
- **Execution-based grading** for the three `build-*` scenarios. Worth doing, but it changes the outcome measure, so it should not change in the same experiment as everything else.

### Sequencing

1. **Finish grader validation.** 18 labelled items. Everything below is measured with this instrument and there is currently no accuracy figure for it.
2. **Correct the regression framing** in README, script and Reddit drafts. This is a live inaccuracy in material about to be published, and it costs nothing to fix.
3. **Author the remaining placebo routes** (8 of 10 outstanding), pre-register, hash.
4. **Fix the padding for depth**, and pre-register that too. Padding chosen for convenience returns whatever answer the padding implies.
5. **Run the 1,152.**

Step 2 is the only one that is urgent, because it is wrong in public right now.
