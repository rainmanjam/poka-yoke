# Baseline-only sample, superseded

Drawn before `_verdicts()` was fixed. `cell.rpartition("_")` split `claude-sonnet-5_with_skill`
into model `claude-sonnet-5_with` / config `skill`, so every treatment cell failed the CURRENT
membership test and 97 with_skill cells were silently excluded. The draw was 60/60 baseline.

What survives: primary vs codex 85% (kappa 0.700), primary vs agy 85% (kappa 0.700), codex vs
agy 90% (kappa 0.794), 12 of 60 contested. Those figures are real **for baseline responses**.

What does not: "disagreement concentrates on baseline runs". Nothing else was sampled, so the
probability of that outcome was 1.
