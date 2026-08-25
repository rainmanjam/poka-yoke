# Poka-Yoke Benchmark

Baseline vs with-skill, blind-graded against pre-written assertions.

All 591 runs answered the scenario prompts currently in the repository.

> **`audit` was not runnable on agy.** the audit skill runs the bundled detector, and agy in print mode refuses to execute a command in EVERY permission mode it offers. Tested: --mode plan and --mode accept-edits both fail with 'permission check failed', and --sandbox denies reads as well. Only --dangerously-skip-permissions executes, and it grants writes too, verified against a canary file, which it overwrote. There is no exec-without-write setting, so the read-only guarantee the other five columns carry cannot be kept while running this skill. That column therefore covers 12 scenarios, not 14; its baseline and with-skill means are still averaged over the same set as each other.

> **Fable 5 is missing `agent-guardrails`, `audit`, `authz`, `build-agent-feature`, `build-endpoint`, `build-form`, `data`, `design`, `guardrails`, `llm`, `ops`, `retro`, `router-nonsoftware`, `ux`.** Those cells were lost to repeated API rate limits and have not been re-collected. The column covers 13 of 14 scenarios; both of its arms are averaged over that same set, so its delta is like-for-like, but it is not directly comparable to a full column.

> **Opus 5 is missing `agent-guardrails`, `audit`, `authz`, `build-agent-feature`, `build-endpoint`, `build-form`, `data`, `design`, `guardrails`, `llm`, `ops`, `retro`, `router-nonsoftware`, `ux`.** Those cells were lost to repeated API rate limits and have not been re-collected. The column covers 13 of 14 scenarios; both of its arms are averaged over that same set, so its delta is like-for-like, but it is not directly comparable to a full column.

> **Sonnet 5 is missing `agent-guardrails`, `audit`, `authz`, `build-agent-feature`, `build-endpoint`, `build-form`, `data`, `design`, `guardrails`, `llm`, `ops`, `retro`, `router-nonsoftware`, `ux`.** Those cells were lost to repeated API rate limits and have not been re-collected. The column covers 13 of 14 scenarios; both of its arms are averaged over that same set, so its delta is like-for-like, but it is not directly comparable to a full column.

> **Haiku 4.5 is missing `agent-guardrails`, `audit`, `authz`, `build-agent-feature`, `build-endpoint`, `build-form`, `data`, `design`, `guardrails`, `llm`, `ops`, `retro`, `router-nonsoftware`, `ux`.** Those cells were lost to repeated API rate limits and have not been re-collected. The column covers 13 of 14 scenarios; both of its arms are averaged over that same set, so its delta is like-for-like, but it is not directly comparable to a full column.

> **Codex is missing `agent-guardrails`, `audit`, `authz`, `build-agent-feature`, `build-endpoint`, `build-form`, `data`, `design`, `guardrails`, `llm`, `ops`, `retro`, `router-nonsoftware`, `ux`.** Those cells were lost to repeated API rate limits and have not been re-collected. The column covers 13 of 14 scenarios; both of its arms are averaged over that same set, so its delta is like-for-like, but it is not directly comparable to a full column.

> **agy is missing `agent-guardrails`, `authz`, `build-agent-feature`, `build-endpoint`, `build-form`, `data`, `design`, `guardrails`, `llm`, `ops`, `retro`, `router-nonsoftware`, `ux`.** Those cells were lost to repeated API rate limits and have not been re-collected. The column covers 12 of 14 scenarios; both of its arms are averaged over that same set, so its delta is like-for-like, but it is not directly comparable to a full column.

## Summary

Spread is `sd`: the standard deviation of pass rates **across scenarios**. It describes how unevenly a model performs over the suite, and is *not* a confidence interval on the mean.

| Model | Baseline | With skill | Delta | Mean time (base → skill) |
|---|---|---|---|---|
| Fable 5 | 88.7% (sd 11.8) | 97.0% (sd 4.0) | **+8.3 pp** | 64s → 92s |
| Opus 5 | 92.7% (sd 7.9) | 96.4% (sd 5.5) | **+3.6 pp** | 130s → 172s |
| Sonnet 5 | 79.8% (sd 12.7) | 88.5% (sd 6.1) | **+8.6 pp** | 88s → 129s |
| Haiku 4.5 | 58.2% (sd 16.7) | 71.1% (sd 24.1) | **+12.9 pp** | 40s → 60s |
| Codex | 74.2% (sd 17.7) | 91.0% (sd 9.8) | **+16.8 pp** | 71s → 97s |
| agy | 64.6% (sd 13.9) | 78.1% (sd 13.2) | **+13.5 pp** | 64s → 71s |

## Per scenario

| Scenario | Fable 5 | Opus 5 | Sonnet 5 | Haiku 4.5 | Codex | agy |
|---|---|---|---|---|---|---|
| | base → skill | base → skill | base → skill | base → skill | base → skill | base → skill |
| `audit` | 100% → 94% | 78% → 94% | 86% → 87% | 70% → 91% | 97% → 97% | ,  |
| `design` | 81% → 100% | 92% → 96% | 86% → 86% | 62% → 62% | 48% → 71% | 57% → 48% |
| `retro` | 100% → 96% | 98% → 97% | 97% → 94% | 89% → 100% | 89% → 89% | 52% → 70% |
| `ux` | 88% → 96% | 84% → 84% | 68% → 77% | 62% → 75% | 67% → 92% | 88% → 79% |
| `authz` | 100% → 100% | 100% → 100% | 94% → 89% | 73% → 90% | 100% → 100% | 67% → 67% |
| `data` | 92% → 88% | 86% → 86% | 70% → 82% | 46% → 71% | 71% → 79% | 75% → 79% |
| `ops` | 83% → 92% | 100% → 100% | 79% → 88% | 29% → 92% | 75% → 92% | 79% → 88% |
| `agent-guardrails` | 83% → 100% | 100% → 100% | 59% → 91% | 33% → 33% | 46% → 100% | 71% → 100% |
| `guardrails` | 75% → 100% | 89% → 98% | 66% → 96% | 54% → 83% | 62% → 100% | 50% → 75% |
| `llm` | 96% → 96% | 95% → 98% | 90% → 89% | 70% → 85% | 85% → 100% | 70% → 85% |
| `build-endpoint` | 61% → 100% | 83% → 100% | 83% → 89% | 44% → 33% | 59% → 81% | 37% → 85% |
| `build-form` | 94% → 100% | 100% → 100% | 67% → 83% | 61% → 78% | 74% → 81% | 63% → 74% |
| `build-agent-feature` | 100% → 100% | 100% → 100% | 94% → 100% | 62% → 31% | 92% → 100% | 67% → 88% |
| `router-nonsoftware` | ,  | ,  | ,  | ,  | ,  | ,  |
