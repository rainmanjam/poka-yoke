# Changelog

All notable changes to this plugin are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Benchmark re-measured across six runtimes: 591 blind-graded runs, thirteen scenarios,
  every run tied to the prompt it answered.** Baseline → with skill:
  Fable 5 88.7% → 97.0% (**+8.3 pp**), Opus 5 92.7% → 96.4% (**+3.6 pp**), Sonnet 5
  79.8% → 88.5% (**+8.6 pp**), Haiku 4.5 58.2% → 71.1% (**+12.9 pp**). All four 95% intervals on
  the paired per-scenario difference exclude zero.
- **Two non-Claude runtimes measured for the first time**, through the same harness, scenarios
  and blind grader: Codex (`gpt-5.6-terra`, read-only sandbox) 74.2% → 91.0% (**+16.8 pp**) and
  Antigravity (`agy`, Gemini 3.1 Pro, plan mode) 64.6% → 78.1% (**+13.5 pp**). These are the
  two largest gains in the suite and they sit on the same headroom curve as the Claude
  columns, so the effect is not a Claude artefact. `audit` cannot run on Antigravity at all: the skill invokes the bundled detector, and `agy` in print mode refuses to execute a command in every permission mode it offers. Only `--dangerously-skip-permissions` runs commands, and it grants writes with them. Across the 77 cells of the six-runtime matrix: 49 improved,
  17 unchanged, 11 regressed. The measured benefit tracks available headroom at r = −0.59 across the six-runtime matrix, and the suite
  closes 39% of remaining headroom, averaged over the 67 cells that have headroom, down from the 71.6% normalized gain this repo
  previously published, which was computed from a broken aggregate.

### Fixed

- **`aggregate()` was reading a subset of the stored runs.** It looped `range(1, --runs + 1)`
  and `--runs` defaults to 3, so re-aggregating after a seven-run sweep counted 264 of 486
  runs: every Opus and Sonnet cell pinned at n=3, printed no warning, and produced a summary
  that looked healthy. It now reads the run directories that exist. The corrected figures moved
  Sonnet 5 from +2.5 pp to +8.6 pp and dissolved an `authz` regression that was about to be
  published as a finding.
- **Model columns averaged different scenario sets.** Sonnet 5's baseline covered 12 scenarios
  and its with-skill column 13, because six runs had failed and left empty directories, so the
  delta subtracted two different suites and the published row did not add up (88.5 − 78.7 =
  9.8, printed as +8.8). Both configurations are now averaged over the scenarios where each ran.
- **An assertion tested layout rather than detection.** *"Notes the SQL injection separately
  from the scoping issue"* failed responses that identified the injection in a heading but
  presented it as a compounding factor inside the tenant-scoping finding. It now asks for the
  injection to be identified as a hazard distinct in kind, anywhere in the response.
- **Editing an assertion left every stored grading scored against the old checklist.**
  `prompt_sha` invalidated a run when its question changed; nothing did the same for its answer
  key. Gradings now record an `assertions_sha` and a run whose checklist has changed is
  regraded rather than reported.
- **A regrade deleted the old grading before producing a new one**, destroying 11 gradings when
  the grader call failed, and because a missing grading merely shrinks a cell, the summary
  printed a model short on one scenario without complaint. The delete is gone; the write
  already overwrote.
- **The `±` in the generated summary was the standard deviation across scenarios**, not a
  confidence interval, but read as one beside a mean. It is now labelled `sd` with a note
  saying what it is, and the README reports real 95% intervals on the paired difference.

### Added

- Five devices in `tests/test_portability.py`, each proven to fail before it passed:
  `test_aggregate_counts_every_run_on_disk`, `test_model_columns_average_the_same_scenarios`,
  `test_no_empty_run_directories`, `test_every_stored_response_has_a_grading`, and
  `test_no_grading_was_scored_against_a_stale_checklist`. Every one of them exists because the
  corresponding instrument failed in a way that looked exactly like a passing result.

### Added

- **Nineteen-runtime support.** Ten native manifests, Claude Code, Codex, Cursor, Devin,
  Kimi, Hermes, Gemini CLI, Grok, Qoder and Kiro, plus an instruction-file install for
  Copilot, Windsurf, Cline, Junie, Zed, Aider and Antigravity, and a vendored path for
  opencode and Pi. `AGENTS.md` is a symlink to `CLAUDE.md` and the runtime-specific context
  files point at it rather than restating it, so there is exactly one source of truth. The
  tiers, and what each one has actually been tested for, are in `docs/install.md`.
- **`scripts/sync_platform_manifests.py`**: generates every derived manifest from
  `plugin.json`; `--check` fails CI if any has drifted. Hand-maintaining them is a chance to
  update all but one, and each stays individually valid while disagreeing with the others.
- **`tests/test_portability.py`**: blocks a runtime-specific path variable, a script path
  that is absolute or does not resolve, a dispatcher that only works when installed, a
  manifest naming a skills directory that does not exist, and a cross-document link pointing
  at a heading that no longer exists.
- **`scripts/cli.py`**: one entry point for the detector and the device registry, so a
  skill names one path rather than remembering which file holds which tool.
- **`.github/workflows/release.yml`**: a tag becomes a release, or nothing does. Refuses a
  tag that disagrees with `plugin.json`, that has no changelog section, or that is not an
  ancestor of `main`. Calls `validate.yml` rather than restating its checks.
- `RELEASING.md`, `CODE_OF_CONDUCT.md`.

- **`scripts/check_cited_rules.py`**: every linter rule the docs recommend is checked
  against the linter that owns it. Rule names are the most perishable thing here, and this
  found `clippy::integer_arithmetic` still recommended after clippy renamed it to
  `arithmetic_side_effects`, plus `ban-ts-comment` attributed to core eslint when it belongs
  to `@typescript-eslint`, and a bare "ruff" citation naming no rule at all, none of ruff's
  969 rules covers a skipped test.
- **Brand assets** in `docs/assets/brand/`: an andon signal tower, the mark of the same
  Toyota system poka-yoke came from. Green sits on top where a real tower puts red: this is
  a ladder, and Control is the rung to climb to. Three cuts, each with a job: badged for
  avatars and favicons, bare for lockups, and a flat one below 32px where shading turns to
  mud. Banners for GitHub, X, YouTube and the README are generated by
  `scripts/make_banners.js` from those files, so they cannot drift from the mark.
- **`scripts/fanout.py`, `review_copy.py`, `find_outreach.py`**: ask Opus, Antigravity and
  Codex the same question independently and have Fable reconcile the answers, so no model
  grades its own work. Used to review every published document and to build
  `private/outreach.md` (gitignored. It is a distribution plan, not documentation).

### Taken from neighbouring projects

Four comparable skill repositories were read closely, affaan-m/ECC,
nextlevelbuilder/ui-ux-pro-max-skill, DietrichGebert/ponytail and addyosmani/agent-skills.
What was adopted, and from where:

- **`scripts/trigger_eval.py`**: deterministic, offline routing evaluation: stemmed TF-IDF
  over the skill descriptions, scored against the prompts a user would actually send. This
  README has long been honest that the skills do not reliably auto-trigger; this is the first
  time that was a number anyone could move. It immediately found `guardrails` and `authz`
  losing to other skills on their own canonical requests, both missing the vocabulary those
  requests use. Rank-1 went 80% → 100% once the descriptions carried it, and CI now holds
  that floor. Borrowed from the Tier-2 evals in
  [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills).
- **`commands/*.toml`**, Codex slash commands, generated from the skills themselves, so a
  command naming a skill that no longer exists is not a possible state. Three of the four
  projects ship these; poka-yoke shipped skills to Codex with no way to invoke a mode by
  name. Prompted by [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail).
- **Grok, Qoder and Kiro manifests**, taking the totals to 19 runtimes and 10 native
  manifests. Free to add because they are generated, and honest to add because the tier table
  files them under "structurally verified, not behaviourally tested". Also from ponytail.
- **Action pinning and a weekly supply-chain workflow.** Every GitHub Action is now pinned to
  a commit SHA: `@v5` is a mutable label, and whoever controls it controls what executes here
  with no diff in this repository for anyone to review. Pinning trades that risk for stale
  pins, so the weekly job reports how far behind each one is rather than letting them rot
  quietly, Control on the pinning, Detection on the drift. Prompted by the supply-chain
  workflows in [affaan-m/ECC](https://github.com/affaan-m/ECC).

Deliberately not adopted: ECC's 286-skill breadth (focus is the point here), and a published
MCP server, poka-yoke is skills-shaped, and an MCP wrapper would be a second surface to keep
in step with the first.

### Changed

- **Skills no longer use `${CLAUDE_PLUGIN_ROOT}`.** Bundled files and scripts are referenced
  relative to the `SKILL.md` that names them. The variable resolved on exactly one runtime
  and silently resolved to nothing on every other runtime, where a skill would reference a file
  it could not read.
- `docs/install.md` rewritten: the vendor-and-rewrite-paths procedure is gone, replaced by
  per-runtime native installs and an honest statement of what is benchmarked (Claude Code)
  versus structurally verified only (everything else).
- CI's `${CLAUDE_PLUGIN_ROOT}`-resolution step replaced by `tests/test_portability.py`. The
  old check worked but was too narrow. It could not see a path variable that was wrong to
  use at all, or a script path that does not resolve.

### Fixed

- **104 documentation findings**, from three models reading every published document and a
  fourth reconciling them. Every one has a recorded disposition, 101 corrected, 2 rejected
  as wrong on inspection, 1 deferred and since fixed. The headline results: the README's
  benchmark prose contradicted its own table on the same page (Haiku's spread was reported
  as worsening when it improved), `docs/method.md` credited Shigeo Shingo with building the
  Toyota Production System when he was an outside consultant who formalised poka-yoke, and
  the hazard catalog promoted a required CI gate to Control, which would have made the
  severity ladder stop discriminating.
- **The suggest hook routed only eight of its ten modes.** The README claimed all ten were
  tested; no test existed, and writing one showed `design` fired only on jargon like
  `typestate` while `retro` had no pattern for "root cause" at all: the two most natural
  ways anyone would ask. Both widened, with one match and one near-miss per mode now under
  test.
- **`release.yml` could not have succeeded.** It ran `uv build` and attached `dist/*` after
  packaging was removed, in the job that runs *after* the tag is pushed, so a release would
  have left a tag behind with nothing attached to it. actionlint passed throughout, because
  the workflow was valid and merely impossible. A test now requires that a workflow building
  a Python distribution has the metadata to build one.
- The detector reported how many `COVERED_BY` *entries* it had, not how many rules those
  entries suppress, under-reporting by three. Three different numbers for the same fact
  were in circulation before it was counted.

### Not done

- **No PyPI or npm release.** A published command would resolve identically on every runtime
  with no path at all, which is why it was attempted. Both registries refuse a new name whose
  punctuation-stripped form matches an existing project, and `pokayoke` is taken on both, registered on PyPI with zero releases, published on npm. `RELEASING.md` step 7 records what
  was checked, the trap in checking it, and the options for revisiting.
- Pi and opencode lose their declarative install with `package.json` gone; vendoring the
  skills directory still works.

## [0.1.0], 2026-08-20

Initial release.

### Added

- **Router skill** (`poka-yoke`) carrying the method: the Control / Warning / Detection
  severity ladder, the contact / fixed-value / motion-step inspection lenses, and Shingo's
  source > self > successive inspection ordering.
- **Ten working modes**: `audit`, `design`, `guardrails`, `retro`, `ux`, `ops`, `data`,
  `authz`, `llm`, `agent-guardrails`.
- **Hazard catalog**: ~30 recurring hazard shapes organized by lens, each with the device
  that closes it and the rung it reaches.
- **Language references** for TypeScript/JavaScript, Python, Rust, and Go, each stating what
  the type system can and cannot enforce.
- **UX pattern reference**: interface devices sized by consequence, including the
  undo-over-confirmation preference order.
- **`detect_hazards.py`**: dependency-free hazard scanner for TypeScript, Python, Go, Rust,
  and SQL, with real AST analysis for Python and diff-aware scanning of changed lines only.
- **Installable device templates** in `assets/devices/`: pre-commit config, GitHub Actions
  gates including migration safety, mistake-prevention lint rule sets for four languages, and
  Claude Code PreToolUse guard hooks.
- **Test suite** covering detector rules and guard-hook behavior, with near-miss cases for
  every rule.
