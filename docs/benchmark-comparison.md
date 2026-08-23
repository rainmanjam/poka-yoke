# How this benchmark compares

Most published skills report no numbers at all. Of the few that do, the methodologies vary
enough that raw percentage-point deltas are not comparable. This page sets out what the
comparable work does, and where this benchmark sits, including where it is weaker.

## The comparable work

| Benchmark | Scope | Trials | Models | Baseline | Blind | Raw data |
|---|---|---|---|---|---|---|
| **[SkillsBench](https://www.skillsbench.ai/leaderboard)** (benchflow-ai) | 87 tasks, general agent skills | 3 | 25 configs | paired |, | on Hugging Face |
| **[CoEvoSkills](https://arxiv.org/pdf/2604.01687)** | self-evolving skills, academic |, | Opus 4.6 | no-skill + human-curated |, | paper |
| **[frontend-design-skill-benchmark](https://github.com/dani-z/frontend-design-skill-benchmark)** | 1 skill, 3 tasks, 18 assertions | 1 | 1 | paired | no | screenshots |
| **[skill-eval-action](https://github.com/skill-bench/skill-eval-action)** | tooling: YAML cases + CI grading |, |, |, |, | n/a |
| **[CC-SKILLS-Evals](https://github.com/AshokNaik009/CC-SKILLS-Evals)** | evaluation suite for skills |, |, |, |, | n/a |
| **poke_yoke** (this repo) | 1 plugin, 13 scenarios (12 on Antigravity), 112 assertions | 1-7 | 6 runtimes | paired | **yes** | committed |

The honest summary of the landscape: **SkillsBench is the serious one.** 87 tasks, up to three
trials, 24 paired model–harness configurations plus one with-skills-only, published
trajectories. Everything else, including this, is smaller and narrower. The single-run,
single-model comparisons that dominate GitHub cannot separate a real effect from run-to-run
noise. Its numbers here are read from the
[`skillsbench@1.1`](https://github.com/benchflow-ai/skillsbench/releases/tag/v1.1) leaderboard,
recomputed 2026-07-16 and retrieved 2026-08-21; the live leaderboard moves.

## Why percentage-point deltas mislead

The most cited skill benchmark result is **+72 pp** (frontend-design: 28% → 100%). This
benchmark's best is **+12.9 pp**. That comparison is meaningless as stated, because the
baselines differ enormously: it is far easier to add 72 points to a 28% baseline than 13 to a
58% one, and this suite's frontier models start above 88%, where fewer than 12 points exist
to win at all.

SkillsBench solves this with **normalized gain**, which measures how much of the *available*
headroom a skill actually closes:

```
g = (with − without) / (100 − without)
```

| | Baseline | With skill | Δ pp | **Normalized gain** |
|---|---|---|---|---|
| **poke_yoke, Fable 5** | 88.7% | 97.0% | +8.3 | **73.7%** |
| **poke_yoke, Opus 5** | 92.7% | 96.4% | +3.6 | **49.6%** |
| **poke_yoke, Sonnet 5** | 79.8% | 88.5% | +8.6 | **43.1%** |
| **poke_yoke, Haiku 4.5** | 58.2% | 71.1% | +12.9 | **30.8%** |
| **poke_yoke, Codex (gpt-5.6-terra)** | 74.2% | 91.0% | +16.8 | **65.1%** |
| **poke_yoke, Antigravity (Gemini 3.1 Pro)** | 64.6% | 78.1% | +13.5 | **38.2%** |
| SkillsBench, Gemini 3.1 Pro (Gemini CLI) | 36.0% | 60.8% | +24.8 | 38.7% |
| SkillsBench, GLM 5.1 | 32.7% | 58.4% | +25.7 | 38.1% |
| SkillsBench, GPT-5.5 (Codex) | 46.8% | 66.5% | +19.7 | 37.0% |
| SkillsBench, Opus 4.7 (Claude Code) | 43.0% | 61.2% | +18.2 | 31.9% |
| SkillsBench, Opus 4.8 (OpenHands) | 45.7% | 54.1% | +8.4 | 15.5% |

Mean normalized gain: **50% here across six runtimes, ~32% across those SkillsBench
configurations**, with this benchmark showing a *smaller* raw delta than most of them.

That per-model figure flatters the result, and the per-cell figure is the honest one. Averaged
over the 67 of 77 scenario×runtime cells that have any headroom left, the skills close **39%** of it; the other ten start at 100%, where normalized gain is undefined, which is
above the SkillsBench average but not by the margin the per-model figure suggests. The gap
between 50% and 39% is Fable 5's 73.7% pulling a six-runtime mean around.

An earlier version of this page reported 71.6%, from figures produced when the aggregator was
reading three runs per cell out of seven. Those numbers were wrong and this table replaces
them.

**Do not read that as "this skill beats SkillsBench."** It does not measure the same thing,
and the next section says why.

## Why this comparison is not apples to apples

Three differences, all of which make this benchmark's target easier:

1. **Task resolution vs. answer quality.** SkillsBench tasks either resolve or do not: an
   objective, binary outcome on real work. This benchmark grades *advice* against a checklist.
   Producing a good answer about a migration is easier than performing one correctly.
2. **The assertions were written by the skill's author.** They were written before the runs
   rather than fitted to them, but they encode a view of what a good answer contains.
   SkillsBench's tasks come with independent, task-defined success criteria.
3. **Scale.** 13 scenarios against 87 tasks; 6 runtimes against 25 configurations.

Where this benchmark is *stronger* than the typical published skill comparison, though not
than SkillsBench, is method: **grading is blind**, cells hold 2-7 runs, the reported spread is
labelled `sd` across scenarios rather than passed off as a confidence interval, every run is
committed with a hash of the prompt it answered, and the harness ships so the numbers can be
re-derived.

## What the comparison suggests

**The gain is applying knowledge, not supplying it.** These models score 58-93% without the
plugin; they already know about idempotency keys and expand/contract migrations. What the
skills add is doing it reliably, which is why the spread matters as much as the mean, Fable 5
falls from sd 11.8 to 4.0 and Sonnet 5 from 12.7 to 6.1.

**The effect is bounded by headroom, and that bound is measurable.** A cell's baseline
correlates with its gain at **r = -0.59** across the 77 cells of the six-runtime matrix.
Cells starting under 50% gain +28.9 pp; cells above 95% lose 0.8 pp. Any comparison against a benchmark with a lower baseline is comparing
positions on that curve, not skill quality.

**Haiku 4.5 gains least in normalized terms** (+12.9 pp, 30.8%), and no longer gains most in points: Codex (+16.8) and Antigravity (+13.5) both exceed it. The
lowest here, in the same range as SkillsBench's fleet. Smaller models convert instructions
into behaviour less reliably. It is also the only model whose *consistency gets worse* with
the skills (sd 16.7 → 24.1): better on average, less predictable.

**None of the benchmarks above reports a regression.** This one publishes eleven, six of them
larger than 5 points, including `build-agent-feature` on Haiku 4.5 at **62% → 31%**: given a
whole feature to build, the smallest model spends its output on the method and ships less of
the thing. That is a difference in reporting convention rather than underlying quality, and it
is worth being sceptical of any skill benchmark that shows only wins.

## Reproducing

```bash
python3 benchmarks/run.py --dry-run     # see the call budget first
python3 benchmarks/run.py --max-calls 450   # the 4 Claude models, 13 scenarios, 3 runs
# Codex and Antigravity are not in the default matrix; add them explicitly:
python3 benchmarks/run.py --models codex-gpt-5.6-terra agy-gemini-3.1-pro --max-calls 250
```

See [`benchmarks/README.md`](../benchmarks/README.md) for the method and its limitations.
