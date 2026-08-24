# Benchmark

Does this plugin actually change what a model produces? This measures it **at the first turn of
a fresh session**, publishes the raw runs, and ships the harness so you can check the numbers
yourself.

Two limits worth knowing before reading any figure below. The baseline arm is *no skill*, not
*a different methodology*, so nothing here separates "this method works" from "any structured
method in context works"; control arms are designed and unrun. And blind grading controls
**bias**, not **accuracy**: two independent cross-vendor graders agree with the primary grader
86% and 88% of the time (Cohen's kappa 0.73 and 0.77), which establishes consistency, not
correctness.

```bash
python3 benchmarks/run.py --max-calls 450              # full sweep
python3 benchmarks/run.py --models opus --runs 1       # quick check
python3 benchmarks/run.py --scenarios ux llm --runs 2  # a couple of modes
python3 benchmarks/run.py --aggregate-only             # re-aggregate existing results
```

Requires Python 3.9+ and the `claude` CLI on your PATH. Reproducing the Codex and
Antigravity columns also needs the `codex` and `agy` CLIs, signed in; without them those two
models are simply absent from the matrix and the other four still run. The sweep is resumable: a run with an existing `response.md` is skipped, so an interrupted sweep continues rather than
starting over.

A full sweep of the four Claude models from nothing is 416 calls, above the default `--max-calls` ceiling of 400, so the
first command raises the ceiling deliberately. That is the ceiling working as intended: a
budget this large should be granted, not defaulted into.

## What it measures

Thirteen scenarios across ten working modes: one advice-shaped scenario per mode, plus three
build-shaped ones. Nine of the advice-shaped scenarios are a realistic message in which **the
user has already applied or proposed a fix that is insufficient**, so agreeing with them scores
badly (`design` is the exception. It is greenfield). That measures whether the model pushes
back with a better device, not whether it can recall a concept when asked directly. The
build-shaped scenarios ask for working code instead, with nobody raising a concern, and
measure what the model reaches for unprompted.

| Scenario | Mode | The insufficient fix the user has already applied |
|---|---|---|
| `audit` | audit | "been through review already" |
| `design` | design |, (asks for a design; measures what shape it reaches for) |
| `retro` | retro | a recent-charge lookup before charging |
| `ux` | ux | an "are you sure?" modal |
| `authz` | authz | "the main query paths are all scoped" |
| `data` | data | a test that the revenue table isn't empty |
| `ops` | ops | green CI on a PR that drops a column |
| `agent-guardrails` | agent-guardrails | rules in CLAUDE.md, in caps, twice |
| `guardrails` | guardrails | a team agreement written up and pinned in Slack |
| `llm` | llm | "be careful" added to the system prompt |
| `build-endpoint` | design |, (asks for a refund endpoint, no concern raised) |
| `build-form` | ux |, (asks for a bulk-delete bar, no concern raised) |
| `build-agent-feature` | llm |, (asks for an email classifier, no concern raised) |

Two scenarios use a code fixture in `fixtures/`; the rest are prose.

## Method

**Two configurations.** `baseline` sends the user's message alone. `with_skill` prepends an
instruction to read the router skill and follow its routing. Nothing else differs.

**Blind grading.** The grader receives the response and the checklist, never which model or
configuration produced it, and never the other configuration's answer. It cannot reward the
skill for sounding like the skill.

**Response runs are structurally read-only, by three different mechanisms.** The four Claude
models get `--allowedTools Read,Grep,Glob`; Codex runs under `--sandbox read-only
--ephemeral`; Antigravity runs under `--mode plan`, which was verified by asking it to
overwrite a canary file and watching it refuse. In each case writing is unrepresentable
rather than merely discouraged. That is the method this plugin argues
for, applied to itself. The grading calls are the gap: they pass no allowlist, and narrowing
them is open work.

**Assertions are behavioural, not vocabulary.** An earlier version of this suite included
"classifies findings with an explicit rung", which only the skill could pass because only the
skill teaches that vocabulary. It was removed. Assertions now test what the response *does*, does it sweep for the whole class, reject the plausible-wrong fix, distinguish reversible from
irreversible, name what it left possible. One holdout survives: the `retro` checklist still
asks whether the response treats the repeat incident as evidence for "a Control-rung device",
which borrows the skill's word for the class of device rather than describing the behaviour.

## Reading the results

`results/benchmark.md` has the summary; `results/benchmark.json` the raw aggregate.
`results/runs/<scenario>/<model>_<config>/run-N/` holds every response, timing, and grading.

Both are generated, `python3 benchmarks/run.py --aggregate-only` rebuilds them from what is
on disk without making a single model call. Aggregate over the **full** matrix: narrowing
`--models` or `--scenarios` rewrites the summary as though the omitted cells do not exist,
which is how the committed aggregate once came to describe one model. The harness prints a
`::warning:: this aggregate is NARROWER than the one it replaces` when that happens, read it
rather than piping it through `tail`.

Each model's two columns are averaged over the scenarios where **both** configurations ran, so
the delta is always a like-for-like difference. Sonnet 5 once had a with-skill cell whose
baseline runs had failed, and the published row subtracted a 13-scenario mean from a
12-scenario one; the numbers in it did not add up.

### Provenance

Every run records a hash of the prompt it answered, and the summary reports how many of the
stored runs still match the prompts in the repository. That line is generated, not written,
so it cannot drift from the data.

Every committed run now carries that hash and matches the prompts in this commit, so the
summary reads `All N runs answered the scenario prompts currently in the repository.` If that
line ever reports a shortfall, the runs behind it were answering a question that has since
been edited.

Gradings carry the same guarantee for the answer key: each records a hash of the assertion
list it was scored against, and a run whose checklist has changed is regraded rather than
reported. Rewriting an assertion used to leave every stored grading scored against a version
that no longer existed.

## The harness has its own devices

An early version of this harness ran 720 calls at 16 concurrent workers, exhausted a session
limit partway through, and then did something worse than stopping: when a call returned
*"You've hit your session limit"*, it saved that text as `response.md`. The file existed, was
the right size, and sat in the right directory, so the run looked successful. The grader
scored those responses 0 out of 8, correctly, since they contained no answer, and **164 of
360 runs, 46% of the sweep, silently became noise** that looked exactly like real data.

It was caught by noticing that three independent runs of one cell all scored 0/8, which is
implausible. That is luck, not process. So the harness now carries devices rather than good
intentions:

| Device | Rung | What it makes impossible |
|---|---|---|
| `--max-calls` ceiling; the harness raises and exits | Control | Overrunning a quota. Not discouraged, impossible. |
| Refuses to **write** a response matching a limit/error pattern | Control | Storing a failure as if it were data |
| `preflight()` runs automatically before every sweep | Control | Starting a run on top of junk |
| Rate-limit detection with exponential backoff | Warning | Mistaking a throttle for malformed output |
| `--dry-run` prints the call budget before spending | Warning | Discovering the cost afterwards |
| 4 workers, 1s pacing, batched grading on a small model |, | Being the reason a limit is hit |
| `aggregate()` reads the run dirs on disk, not `--runs` | Control | Averaging a subset of what was measured |
| Gradings record an `assertions_sha`; a changed checklist forces a regrade | Control | Reporting a score against a superseded answer key |
| Each model's columns average only scenarios where both configs ran | Control | A delta that subtracts two different suites |
| A narrower aggregate than the one it replaces prints a warning | Warning | Silently overwriting a full result with a partial one |

Two of those are worth calling out because the bugs behind them are shapes from the catalog,
found in the harness itself. Writing the limit message as a response was **X2, silent
coercion**: a failure converted into a plausible-looking value. And the budget check
originally counted only grading for runs that already existed, ignoring the ones it was about
to create, so it under-reported the cost of its own plan: a count that passed while the set it
counted was incomplete, which is the **fixed-value lens** in miniature.

Run `python3 benchmarks/run.py --preflight` any time to audit stored data, and
`--preflight --purge-suspect` to delete what it finds and regenerate it.

## Known limitations

- **Grading is by a model, not a human.** Consistent, but it inherits that model's judgment.
  Four of the six graded runtimes are Claude models and the default grader is one of them, Haiku 4.5 is
  graded by itself.
- **Assertions were written by the same author as the skill.** They encode a view of what a
  good answer looks like. They were written before the runs, not fitted to them, but that is
  not the same as being independent.
- **Ceiling effects.** Stronger models saturate several scenarios at 100%, which hides any
  further difference between configurations. This is not a footnote: the measured benefit
  tracks available headroom closely (r = -0.52 between a cell's baseline and its delta), so
  the aggregate numbers depend heavily on which scenarios are in the suite.
- **Cells hold 1-7 runs.** The per-scenario means the summary averages are themselves noisy,
  and unevenly so. Four cells hold a **single** run, `build-agent-feature` for Fable 5
  baseline and both Opus 5 configurations, because repeated attempts across three separate
  windows returned rate limits and the harness gave up after its retries rather than storing
  the error as data. Those cells have no variance estimate and are the first thing to
  backfill; all three currently read 100%, so a second run can only confirm or lower them.
- **Three runtimes are measured, not nineteen.** Claude Code, Codex and Antigravity run
  through this harness; the other sixteen install targets in `docs/install.md` are
  structurally verified and behaviourally untested.
- **The runtimes answer at very different lengths**: a Codex reply runs 50-200 words where a
  Claude answer runs 400-800, and Antigravity delivers a written plan rather than a chat
  reply. The same checklist lands differently against each, so only the delta *within* a
  runtime is a fair comparison; the absolute pass rates are not directly comparable across
  the six columns.
- **Cost is not measured directly.** Wall-clock and output length stand in for it; the harness
  does not read token counts back from the CLI.

If you re-run this and get materially different numbers, that is worth an issue: the point of
shipping the harness is that the claims are checkable.
