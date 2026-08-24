#!/usr/bin/env python3
"""What the documentation claims must match the code and the data it describes.

Named for the portability rules it started with; it now guards every claim a reader could
check for themselves, paths, links, the layout tree, and the benchmark figures.

The skills ship to 19 runtimes. These are the constraints that make that true.

Portability is not a property you achieve once. It is a property that decays the moment
someone writes the convenient thing. `${CLAUDE_PLUGIN_ROOT}/references/foo.md` works
perfectly on the runtime you are testing on and silently resolves to nothing on the other
eight, where it degrades into a skill that references a file it cannot read.

Nothing about that failure is visible from inside Claude Code, which is exactly why it needs
a test rather than a note in CONTRIBUTING.md.

Run: python3 tests/test_portability.py
"""

import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "poka-yoke"
SKILLS = sorted((PLUGIN / "skills").glob("*/SKILL.md"))

# Everywhere a runnable command is documented.
DOCUMENTED = SKILLS + [REPO / "README.md", REPO / "docs" / "install.md",
                       REPO / "RELEASING.md"]

try:
    import tomllib
except ModuleNotFoundError:      # pragma: no cover - Python < 3.11
    tomllib = None


def commands_in(path: Path) -> str:
    """Only fenced code blocks. Those are what a reader copies and runs.

    Scanning prose too was over-broad: RELEASING.md legitimately names the *wrong*
    invocation while explaining why it does not work, and a document must be able to warn
    about a command without the warning itself failing the check.
    """
    return "\n".join(re.findall(r"```[a-z]*\n(.*?)```", path.read_text(), re.S))


class TestNoRuntimeSpecificPaths(unittest.TestCase):
    """Rule 1: a skill may not name a path that only one runtime can resolve."""

    # ${CLAUDE_PLUGIN_ROOT} is the one we shipped, but any shell-style variable in a path
    # has the same problem, so catch the shape rather than the single name.
    VAR = re.compile(r"\$\{[A-Z_][A-Z0-9_]*\}")

    def test_no_path_variables_in_skills(self):
        for f in SKILLS:
            hits = self.VAR.findall(f.read_text())
            self.assertEqual(
                [], hits,
                f"{f.relative_to(REPO)} uses a runtime-specific path variable {hits}. "
                "Reference bundled files relative to this SKILL.md instead.")

    def test_relative_references_all_resolve(self):
        pattern = re.compile(r"\.\./\.\./[A-Za-z0-9_./-]+")
        checked = 0
        for f in SKILLS:
            for rel in sorted(set(pattern.findall(f.read_text()))):
                # `../../references/lang-*.md` names a family, not a file. Resolve the glob
                # and require it to match something; the literal string never will.
                if "*" in rel or rel.endswith("-"):
                    stem = rel.rstrip("-")
                    matches = list(f.parent.glob(stem.replace("*", "*") + "*"))
                    self.assertTrue(
                        matches,
                        f"{f.relative_to(REPO)} points at {rel}, which matches nothing")
                    checked += 1
                    continue
                target = (f.parent / rel).resolve()
                self.assertTrue(
                    target.exists(),
                    f"{f.relative_to(REPO)} points at {rel}, which does not exist")
                checked += 1
        self.assertGreater(checked, 0, "found no relative references, is the probe broken?")


class TestNoShellingOutByPath(unittest.TestCase):
    """Rule 2: a script path must be relative to the skill that names it, never absolute and
    never a runtime-specific variable."""

    def test_scripts_are_invoked_by_a_relative_path(self):
        """A script path must be relative to the SKILL.md that names it.

        `${CLAUDE_PLUGIN_ROOT}/scripts/detect_hazards.py` resolves on exactly one runtime.
        `../../scripts/detect_hazards.py` resolves anywhere the skills and scripts are
        vendored together, because an agent that just read the skill knows where it is.
        """
        pattern = re.compile(r"python3?\s+([^\s`\"']+\.py)")
        checked = 0
        for f in SKILLS:
            for path in set(pattern.findall(commands_in(f) + " " + f.read_text())):
                self.assertFalse(
                    path.startswith("/") or "${" in path,
                    f"{f.relative_to(REPO)} invokes {path}, absolute or runtime-specific")
                if path.startswith("../"):
                    target = (f.parent / path).resolve()
                    self.assertTrue(target.exists(),
                                    f"{f.relative_to(REPO)} invokes {path}, which does not exist")
                    checked += 1
        self.assertGreater(checked, 0, "no script invocations found, is the probe broken?")

    def test_the_dispatcher_runs_without_being_installed(self):
        """cli.py is executed as a plain file, so it must not rely on package-relative
        imports. It did briefly, which only showed up when run outside a wheel."""
        cli = PLUGIN / "scripts" / "cli.py"
        self.assertTrue(cli.exists())
        self.assertNotIn("from .", cli.read_text(),
                         "cli.py uses a package-relative import but is run as a script")
        r = subprocess.run([sys.executable, str(cli), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("detect", r.stdout)


class TestWorkflowsCanActuallySucceed(unittest.TestCase):
    """A valid workflow is not the same as a workflow that can pass.

    `release.yml` ran `uv build` and attached `dist/*` for weeks after packaging was removed.
    actionlint was happy: the YAML was correct and the shell parsed. It would simply have
    failed at run time, in the job that runs *after* the tag is pushed, leaving a tag with no
    release behind it. Nothing catches that, because release workflows only run on a tag.
    """

    WF = REPO / ".github" / "workflows"

    @staticmethod
    def _uncommented(path: Path) -> str:
        """YAML comments explaining why a step was REMOVED must not read as the step.

        The first version of this check flagged release.yml for a `uv build` that existed
        only inside the comment recording its deletion."""
        out = []
        for line in path.read_text().splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            out.append(line.split(" #", 1)[0] if " #" in line else line)
        return "\n".join(out)

    def test_python_build_steps_have_something_to_build(self):
        for wf in sorted(self.WF.glob("*.yml")):
            body = self._uncommented(wf)
            if not re.search(r"\b(uv build|python -m build|poetry build|hatch build)\b", body):
                continue
            self.assertTrue(
                (REPO / "pyproject.toml").exists() or (REPO / "setup.py").exists(),
                f"{wf.name} builds a Python distribution, but the repository has no "
                "pyproject.toml or setup.py: the job would fail at run time")

    def test_npm_publish_steps_have_a_package(self):
        for wf in sorted(self.WF.glob("*.yml")):
            if re.search(r"^\s*(run:.*)?npm publish", self._uncommented(wf), re.M):
                self.assertTrue((REPO / "package.json").exists(),
                                f"{wf.name} runs `npm publish` with no package.json")

    def test_release_attaches_only_artefacts_it_produces(self):
        rel = self.WF / "release.yml"
        if not rel.exists():
            self.skipTest("no release workflow")
        body = self._uncommented(rel)
        if "dist/" in body:
            self.assertIn("uv build", body,
                          "release.yml attaches dist/* but never builds it")


class TestBadgesMatchTheSupportTiers(unittest.TestCase):
    """A badge is a claim, and the tier table is where that claim is decided.

    They drifted the day the manifests landed: Codex and Cursor gained native manifests
    while their badges still read `adapted`. A badge is the first thing a reader sees and
    the last thing anyone thinks to update.
    """

    TIER_WORD = {"Benchmarked": "benchmarked", "Native manifest": "native",
                 "Instruction file": "instruction", "Vendored": "vendored"}

    def _tiers(self) -> dict:
        """runtime name -> the tier word its badge should carry."""
        out = {}
        for line in (REPO / "docs" / "install.md").read_text().splitlines():
            m = re.match(r"\|\s*\*\*(.+?)\*\*\s*\|.*\|\s*(.+?)\s*\|$", line)
            if not m or m.group(1) not in self.TIER_WORD:
                continue
            for runtime in m.group(2).split(","):
                out[runtime.strip().lower()] = self.TIER_WORD[m.group(1)]
        return out

    def test_counted_badges_match_reality(self):
        """A badge is the most-read claim in the repository and the least-edited.

        `runtimes-9` survived a change that left seven runtimes with a manifest and sixteen
        documented. It matched neither. Anything a badge counts has to be counted from the
        thing itself.
        """
        readme = (REPO / "README.md").read_text()
        badges = dict((n, v) for n, v, _ in
                      re.findall(r"img\.shields\.io/badge/([^-]+)-([^-]+)-([^)\]]+)", readme))

        skills = len([d for d in (PLUGIN / "skills").iterdir() if d.is_dir()])
        registry = (REPO / "docs" / "poka-yoke" / "registry.md").read_text()
        devices = len(re.findall(r"^\| `", registry, re.M))
        runtimes = sum(len(m.group(2).split(","))
                       for line in (REPO / "docs" / "install.md").read_text().splitlines()
                       for m in [re.match(r"\|\s*\*\*(.+?)\*\*\s*\|.*\|\s*(.+?)\s*\|$", line)]
                       if m and m.group(1) in self.TIER_WORD)

        expected = {"runtimes": str(runtimes), "skills": str(skills),
                    "devices%20in%20CI": str(devices)}
        checked = 0
        for key, want in expected.items():
            if key not in badges:
                continue
            checked += 1
            self.assertEqual(want, badges[key],
                             f"badge `{key}` says {badges[key]}, reality is {want}")
        self.assertGreater(checked, 1, "matched almost no counted badges, probe broken")

    def test_benchmarked_badges_match_the_aggregate(self):
        """A `-benchmarked` badge must name a runtime that is actually in benchmark.json.

        The counted badges (runtimes, skills, devices) have been guarded for a while; the
        claim badges were plain prose. `Only the Claude Code path is benchmarked` sat in
        install.md for a day after two more runtimes had 500+ runs behind them, because
        nothing tied the sentence to the data. A badge asserting a measurement should fail
        when the measurement is absent.
        """
        agg = REPO / "benchmarks" / "results" / "benchmark.json"
        if not agg.exists():
            self.skipTest("no aggregate committed")
        labels = {v["label"] for v in json.loads(agg.read_text())["by_model"].values()}
        # the badge says the product name; the aggregate labels the model inside it
        ALIAS = {"Claude Code": {"Fable 5", "Opus 5", "Sonnet 5", "Haiku 4.5"},
                 "Codex": {"Codex"}, "Antigravity": {"agy"}}
        readme = (REPO / "README.md").read_text()
        claimed = re.findall(r"img\.shields\.io/badge/([A-Za-z_]+)-benchmarked-", readme)
        self.assertTrue(claimed, "no benchmarked badges found, is the probe broken?")
        for name in claimed:
            product = name.replace("_", " ")
            self.assertIn(product, ALIAS,
                          f"badge claims {product} is benchmarked; this test has no mapping "
                          f"for it, so either add one or the badge is wrong")
            self.assertTrue(
                ALIAS[product] & labels,
                f"badge says {product} is benchmarked, but benchmark.json holds no runs "
                f"for it (has: {sorted(labels)})")

    def test_trade_table_figures_come_from_the_gradings(self):
        """Every percentage in the README's "What it trades" table must be recomputable.

        That table is the positioning: it claims the skills make responses more constructive
        and worse at spotting the defect in front of them. Both halves are load-bearing, and
        the unflattering half is what makes the flattering half credible, so a drifted figure
        there costs more than a drifted figure in the summary table.

        Rounding is specified here rather than left to the writer. A first attempt at checking
        these by hand used floor division and reported four of five as wrong by one point,
        which nearly produced a commit "correcting" four accurate numbers.
        """
        readme = (REPO / "README.md").read_text()
        m = re.search(r"## What it trades\n(.*?)\n---", readme, re.S)
        self.assertTrue(m, "no 'What it trades' section; if it moved, this probe checks nothing")
        rows = re.findall(r"^\| ([^|]+?) \| (\d+)% \| \*\*(\d+)%\*\* \|$", m.group(1), re.M)
        self.assertGreaterEqual(len(rows), 4,
                                f"parsed {len(rows)} rows from the trade table, expected the "
                                f"full set; the probe is matching the wrong shape")

        runs = REPO / "benchmarks" / "results" / "runs"
        if not runs.exists():
            self.skipTest("no stored runs")
        CURRENT = {"fable", "opus", "claude-sonnet-5", "claude-haiku-4-5-20251001",
                   "codex-gpt-5.6-terra", "agy-gemini-3.1-pro"}

        def arm(cell):
            for suffix in ("baseline", "with_skill"):
                if cell.endswith("_" + suffix):
                    return cell[: -(len(suffix) + 1)], suffix
            return None, None

        tally = {}
        for g in runs.glob("*/*/*/grading.json"):
            model, config = arm(g.parts[-3])
            if model not in CURRENT or config is None:
                continue
            for e in json.loads(g.read_text()).get("expectations", []):
                tally.setdefault(e.get("text", ""), {"baseline": [], "with_skill": []})
                tally[e["text"]][config].append(bool(e.get("passed")))

        # The table paraphrases each assertion, so match on a distinctive fragment rather
        # than on equality: the wording in the README is for a reader, not for this test.
        FRAGMENTS = {
            "concrete device": "Proposes a concrete device per finding",
            "bypassable": "Notes that pre-commit is bypassable",
            "injection vector": "Identifies the raw interpolation",
            "silently wrong number": "Explains why a silently wrong number",
        }
        checked = 0
        for label, claimed_b, claimed_w in rows:
            key = next((v for frag, v in FRAGMENTS.items() if frag in label), None)
            if key is None:
                continue                      # "Names what the design makes impossible" is a
                                              # family, covered by its own aggregate elsewhere
            match = [k for k in tally if k.startswith(key)]
            self.assertTrue(match, f"README row {label!r} names no assertion in the gradings")
            d = tally[match[0]]
            got_b = round(sum(d["baseline"]) * 100 / len(d["baseline"]))
            got_w = round(sum(d["with_skill"]) * 100 / len(d["with_skill"]))
            self.assertEqual((int(claimed_b), int(claimed_w)), (got_b, got_w),
                             f"README trade table says {claimed_b}% -> {claimed_w}% for "
                             f"{label!r}; the gradings say {got_b}% -> {got_w}%")
            checked += 1
        self.assertGreaterEqual(checked, 4,
                                f"only verified {checked} trade-table rows against the data")

    def test_regression_count_is_stated_against_its_null(self):
        """A count of negative cells means nothing without the count chance alone produces.

        The README said "Nine of 52 cells regressed" for weeks, and it read as an honest
        caveat. It was the opposite. Simulating the null of no effect from the real per-cell
        run counts puts the expected number of negative cells at about 18, so nine is *below*
        what noise gives: the scarcity of regressions was evidence the effect is consistent,
        and it was being published as though it were evidence of harm.

        The failure mode is specific and will recur: a modest-sounding number is never
        challenged, because nobody audits a claim that undersells. So the rule is mechanical.
        Wherever the README states how many cells regressed, the null has to be on the page
        with it.
        """
        # Normalise before matching. The claim in the NOTE box wraps as "cells came out"
        # then "> negative", so a regex over raw text matched only the claim that happened to
        # sit on one line, and the most visible statement in the README was invisible to the
        # check guarding it. Collapse blockquote markers and newlines first.
        readme = re.sub(r"\s*\n>?\s*", " ", (REPO / "README.md").read_text())
        # finditer, not findall + index. The first version looked up each claim's position
        # with readme.index(), which returns the FIRST occurrence, so every claim was checked
        # against the same window: stripping the null from the NOTE box left the test green
        # because the section further down still had one. A checker that cannot fail for the
        # second instance of the thing it checks is the bug it exists to prevent.
        claims = list(re.finditer(
            r"(\w+|\d+) of (?:the )?(\d+) cells (?:came out negative|regressed)", readme))
        self.assertTrue(claims,
                        "found no regression-count claim in the README; if the wording moved, "
                        "this probe is checking nothing and needs updating with it")
        for m in claims:
            count, total = m.group(1), m.group(2)
            window = readme[m.start():m.start() + 600]
            self.assertRegex(
                window, r"chance alone|null|noise alone",
                f"the README says {count} of {total} cells came out negative without naming "
                f"what chance alone would produce. A regression count published on its own "
                f"reads as evidence of harm when it is usually evidence of noise.")

    def test_grader_validator_sees_every_arm(self):
        """The validation sampler must reach every arm on disk, not just the ones its cell
        parser happens to split correctly.

        It shipped splitting `results/runs/<scenario>/<model>_<config>/` with
        `cell.rpartition("_")`, which cuts at the LAST underscore. `..._baseline` parsed;
        `..._with_skill` became model `<model>_with` and config `skill`, failed the
        known-models test, and was dropped. 97 treatment cells vanished, the sampler drew 60
        baseline items, printed a success line, and the conclusion drawn from that sample was
        an artifact of the bug. Half the population was missing and nothing went red.

        Parsing is asserted directly rather than through a drawn sample, so this fails on the
        bug itself instead of on a statistical shadow of it.
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_grader", REPO / "benchmarks" / "validate_grader.py")
        vg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vg)

        for model in ("claude-sonnet-5", "fable", "agy-gemini-3.1-pro", "codex-gpt-5.6-terra"):
            for cfg in vg.CONFIG_SUFFIXES:
                got = vg._split_cell(f"{model}_{cfg}")
                self.assertEqual(got, (model, cfg),
                                 f"{model}_{cfg} parsed as {got}; a config containing an "
                                 f"underscore must not be split at the wrong boundary")
        self.assertIsNone(vg._split_cell("claude-sonnet-5_nonsense"),
                          "an unknown suffix must be rejected, not guessed at")

        # And the arms the harness can produce must all be parseable, so adding a config to
        # run.py without teaching the validator about it fails here rather than silently
        # shrinking the population it samples from.
        run_src = (REPO / "benchmarks" / "run.py").read_text()
        m = re.search(r"^CONFIGS = \[(.*?)\]", run_src, re.M | re.S)
        self.assertTrue(m, "could not find CONFIGS in run.py, is this probe broken?")
        configs = re.findall(r'"([a-z_]+)"', m.group(1))
        self.assertTrue(configs, "parsed no configs out of run.py, is this probe broken?")
        missing = [c for c in configs if c not in vg.CONFIG_SUFFIXES]
        self.assertEqual(missing, [],
                         f"run.py produces {missing} but the validation sampler cannot parse "
                         f"those cells, so it would silently exclude them")

    def test_shipped_devices_carry_a_marker(self):
        """A device nobody marked is invisible to the registry that claims to list them all.

        `docs/poka-yoke/registry.md` opens with "every mistake-proofing device in this
        repository". It lists what someone remembered to annotate. The generator already
        over-counted once by reading its own docstring examples; this is the same fault in
        the other direction, and it is the one that matters, because a missing row looks
        exactly like a device that does not exist.

        The shipped guard hooks are the case worth pinning: they are the plugin's own
        Control-rung examples, and a reader who greps the registry for them should find them.
        """
        marked = {p for p in (REPO / "plugins/poka-yoke/assets/devices").rglob("*")
                  if p.is_file() and p.suffix in {".py", ".yaml", ".yml"}
                  and "poka-yoke:" in p.read_text(errors="ignore")}
        shipped = {p for p in (REPO / "plugins/poka-yoke/assets/devices").rglob("*")
                   if p.is_file() and p.suffix in {".py", ".yaml", ".yml"}}
        self.assertTrue(shipped, "no shipped device files found - is this probe reading the right tree?")
        unmarked = sorted(str(p.relative_to(REPO)) for p in shipped - marked)
        self.assertEqual(
            unmarked, [],
            "these ship as devices but carry no `poka-yoke:` marker, so the registry that "
            "claims to list every device does not list them:\n  " + "\n  ".join(unmarked))

    def test_zero_dependency_badge_is_true(self):
        """The claim people act on before installing. It has to survive someone adding a
        dependency manifest without thinking about the badge."""
        readme = (REPO / "README.md").read_text()
        if "dependencies-zero" not in readme:
            self.skipTest("no dependency badge")
        manifests = [n for n in ("requirements.txt", "setup.py", "pyproject.toml",
                                 "package.json", "Pipfile", "poetry.lock")
                     if (REPO / n).exists()]
        self.assertEqual([], manifests,
                         f"README claims zero dependencies but {manifests} exist")

    def test_every_runtime_badge_states_its_real_tier(self):
        tiers = self._tiers()
        self.assertTrue(tiers, "could not parse the tier table, is the probe broken?")
        badges = re.findall(r"img\.shields\.io/badge/([^-]+)-([^-]+)-", 
                            (REPO / "README.md").read_text())
        self.assertTrue(badges, "no shields.io badges found in README")

        checked = 0
        for raw_name, claim in badges:
            name = raw_name.replace("_", " ").lower()
            if name not in tiers:          # non-runtime badges (counts, licence, …)
                continue
            checked += 1
            self.assertEqual(
                tiers[name], claim.lower(),
                f"README badge says {raw_name} is '{claim}', but docs/install.md places it "
                f"in the '{tiers[name]}' tier")
        self.assertGreater(checked, 2,
                           "matched almost no runtime badges: the probe is broken")


class TestDocsMatchTheTree(unittest.TestCase):
    """Documentation that names a directory must name one that exists.

    The plugin README listed the skills as `poka-yoke-audit/`, `poka-yoke-design/` and so on
    for every mode: a naming scheme the repository had already moved away from. Ten of
    eleven paths were wrong, in the file whose entire job is to describe the layout, and
    nothing noticed: the link checker only looks at markdown links, and a directory tree in
    a fenced block is neither a link nor code that runs.
    """

    DOCS = [REPO / "README.md", REPO / "plugins" / "poka-yoke" / "README.md",
            REPO / "docs" / "install.md", REPO / "CLAUDE.md", REPO / "CONTRIBUTING.md"]

    def test_every_skill_is_documented(self):
        names = {d.name for d in (PLUGIN / "skills").iterdir() if d.is_dir()}
        for doc in [REPO / "README.md", PLUGIN / "README.md"]:
            txt = doc.read_text()
            missing = {n for n in names if n not in txt}
            self.assertEqual(set(), missing,
                             f"{doc.relative_to(REPO)} does not mention skill(s): "
                             f"{sorted(missing)}")

    def test_the_router_dispatches_to_every_skill(self):
        """The router's table is how the other ten modes are reachable at all.

        A mode that is not in it is installed, documented, and unreachable: the failure is
        invisible because everything about the skill itself is fine.
        """
        router = PLUGIN / "skills" / "poka-yoke" / "SKILL.md"
        text = router.read_text()
        missing = [d.name for d in sorted((PLUGIN / "skills").iterdir())
                   if d.is_dir() and d.name != "poka-yoke" and d.name not in text]
        self.assertEqual([], missing,
                         f"the router does not dispatch to: {missing}. Add them to the "
                         "dispatch table in skills/poka-yoke/SKILL.md")

    def test_no_doc_names_a_skill_directory_that_does_not_exist(self):
        real = {d.name for d in (PLUGIN / "skills").iterdir() if d.is_dir()}
        # Both the current shape (`skills/<name>/`) and the retired one (`poka-yoke-<name>/`).
        pattern = re.compile(r"(?:skills/|├──\s+|└──\s+)([a-z][a-z-]*)/")
        for doc in self.DOCS:
            if not doc.exists():
                continue
            for name in set(pattern.findall(doc.read_text())):
                if name.startswith("poka-yoke-") or name in {n for n in real}:
                    self.assertIn(
                        name, real,
                        f"{doc.relative_to(REPO)} names skills/{name}/, which does not exist "
                        f"(skills are: {sorted(real)})")


class TestBenchmarkClaimsMatchTheData(unittest.TestCase):
    """The headline numbers must equal what the committed aggregate says.

    They diverged once, and invisibly: a partial re-run of one scenario against one model
    overwrote `benchmark.json` with four runs, while the README went on quoting 240. Anyone
    following the README to the data it pointed at would have found a file that appeared to
    contradict it. The numbers were right the whole time; the evidence for them was gone.
    """

    AGG = REPO / "benchmarks" / "results" / "benchmark.json"

    def test_aggregate_counts_every_run_on_disk(self):
        """A cell's n must equal the runs actually graded for it.

        `aggregate()` used to loop `range(1, --runs + 1)`, and `--runs` defaults to 3. So
        `--aggregate-only` after a 7-run sweep averaged run-1..run-3 and ignored the rest:
        264 of 486 runs counted, every Opus and Sonnet cell pinned at n=3, no warning
        printed, and a published table that looked perfectly healthy. The corrected numbers
        moved Sonnet 5 from +2.5 pp to +8.5 pp and dissolved an `authz` regression that had
        been about to be written up as a finding.

        Nothing about the output said "half your data is missing", which is why this is a
        test and not a comment.
        """
        if not self.AGG.exists():
            self.skipTest("no aggregate committed")
        runs_root = REPO / "benchmarks" / "results" / "runs"
        if not runs_root.is_dir():
            self.skipTest("no runs committed")
        data = json.loads(self.AGG.read_text())

        checked, short = 0, []
        for scenario, cells in data["scenarios"].items():
            for cell, v in cells.items():
                graded = len(list((runs_root / scenario / cell).glob("run-*/grading.json")))
                checked += 1
                if v["n"] != graded:
                    short.append(f"{scenario}/{cell}: aggregate n={v['n']}, graded on disk={graded}")

        self.assertTrue(checked, "no cells compared, is this probe reading the right tree?")
        self.assertEqual(short, [], "aggregate ignores graded runs:\n  " + "\n  ".join(short))

    def test_readme_figures_come_from_the_committed_aggregate(self):
        if not self.AGG.exists():
            self.skipTest("no aggregate committed")
        data = json.loads(self.AGG.read_text())
        readme = (REPO / "README.md").read_text()
        # Read the summary table, not the prose. The prose form changed once: a rewrite
        # moved from "Fable 5 **85.8% → 97.9%**" to "Haiku 4.5 goes **52.9% → 75.7%**", and
        # a probe keyed to the old phrasing found nothing to check. It failed loudly only
        # because of the assertTrue below; without that it would have passed while verifying
        # zero claims, which is the exact shape of a check that cannot fail.
        # The name list used to be hardcoded to the four Claude models, with an
        # assertEqual(len, 4) pinning it there. Codex and agy were then added to the
        # aggregate and quoted in their own table, and the probe went on checking four rows
        # and passing, so the two largest gains in the suite (+16.8 and +13.5 pp) were
        # unverified prose. Match any bolded row and take the expected set from the data, so
        # a seventh runtime cannot be quoted without being checked.
        claimed = {m[0]: (float(m[1]), float(m[2])) for m in re.findall(
            r"\|\s*\*\*([A-Za-z][A-Za-z0-9 .\-]*)\*\*\s*\|\s*([\d.]+)%[^|]*\|"
            r"\s*([\d.]+)%[^|]*\|", readme)}
        self.assertTrue(claimed, "no benchmark figures found in README, is the probe broken?")

        actual = {v["label"]: (round(v["baseline"]["pass_rate"] * 100, 1),
                               round(v["with_skill"]["pass_rate"] * 100, 1))
                  for v in data["by_model"].values()}
        unquoted = sorted(set(actual) - set(claimed))
        self.assertEqual(
            unquoted, [],
            f"benchmark.json holds runs for {unquoted} but the README quotes no figures for "
            f"them, so those numbers are unguarded; found rows for {sorted(claimed)}")
        for label, (b, s) in claimed.items():
            self.assertIn(label, actual, f"README quotes {label}, absent from benchmark.json")
            self.assertAlmostEqual(b, actual[label][0], delta=0.1,
                                   msg=f"{label} baseline: README {b}%, data {actual[label][0]}%")
            self.assertAlmostEqual(s, actual[label][1], delta=0.1,
                                   msg=f"{label} with-skill: README {s}%, data {actual[label][1]}%")

    def test_no_empty_run_directories(self):
        """A run directory with no response is a failed run, and it leaves no other trace.

        `do_run` creates the directory before it calls the model. Six runs failed during a
        sweep and left exactly this: empty directories, no `FAIL` line that survived, and a
        summary table that simply had fewer cells. The absence of data looked like the shape
        of the matrix rather than like six errors.
        """
        runs_root = REPO / "benchmarks" / "results" / "runs"
        if not runs_root.is_dir():
            self.skipTest("no runs committed")
        empty = [str(d.relative_to(runs_root))
                 for d in runs_root.glob("*/*/run-*")
                 if d.is_dir() and not (d / "response.md").exists()]
        self.assertEqual(
            empty, [],
            f"{len(empty)} run director(ies) hold no response: the run failed:\n  "
            + "\n  ".join(sorted(empty)[:10]) + ("\n  ..." if len(empty) > 10 else ""))

    def test_model_columns_average_the_same_scenarios(self):
        """Baseline and with-skill must be averaged over an identical scenario set.

        Otherwise the delta subtracts two different suites. That happened: Sonnet 5's
        baseline covered 12 scenarios and its with-skill column 13, and the published row
        read 78.7% -> 88.5% with a delta of +8.8 pp, which is not the difference between
        those two numbers. A summary whose own arithmetic does not close is worse than no
        summary, because it still looks like one.
        """
        if not self.AGG.exists():
            self.skipTest("no aggregate committed")
        data = json.loads(self.AGG.read_text())
        for model, v in data["by_model"].items():
            b, w = v.get("baseline"), v.get("with_skill")
            if not (b and w):
                continue
            self.assertEqual(
                b["scenarios"], w["scenarios"],
                f"{v['label']}: baseline averages {b['scenarios']} scenarios, "
                f"with_skill {w['scenarios']}: the delta compares different suites")
            self.assertAlmostEqual(
                v["delta_pp"], round(100 * (w["pass_rate"] - b["pass_rate"]), 1), delta=0.11,
                msg=f"{v['label']}: delta_pp does not equal with_skill minus baseline")

    def test_every_stored_response_has_a_grading(self):
        """A response with no grading silently shrinks its cell instead of raising.

        `grade_cell` once deleted a stale grading before regrading it. When the grader call
        failed, nothing was left, and because `aggregate()` simply skips a run with no
        grading.json, the cell got quietly smaller. Eleven gradings went that way and
        `authz` lost Sonnet 5 altogether; the summary table printed without complaint,
        one model short on one scenario.

        Missing data must look like a failure, not like a smaller sample.
        """
        runs_root = REPO / "benchmarks" / "results" / "runs"
        if not runs_root.is_dir():
            self.skipTest("no runs committed")
        orphans = [str(r.parent.relative_to(runs_root))
                   for r in runs_root.glob("*/*/run-*/response.md")
                   if not (r.parent / "grading.json").exists()]
        self.assertEqual(
            orphans, [],
            f"{len(orphans)} response(s) stored with no grading, re-grade them:\n  "
            + "\n  ".join(sorted(orphans)[:10]) + ("\n  ..." if len(orphans) > 10 else ""))

    def test_no_grading_was_scored_against_a_stale_checklist(self):
        """Every committed grading must name the assertions it was actually scored against.

        `prompt_sha` already invalidates a run when its question is edited. Nothing did the
        same when an *assertion* was edited: `grade_cell` skipped any run that already had a
        grading.json, so a rewritten checklist left every stored grading scored against a
        version that no longer existed, and the aggregate reported them without comment.

        A pass rate is only a measurement while you can say what it was measured against.
        """
        runs_root = REPO / "benchmarks" / "results" / "runs"
        scen_file = REPO / "benchmarks" / "scenarios.json"
        if not runs_root.is_dir() or not scen_file.exists():
            self.skipTest("no benchmark data committed")
        raw = json.loads(scen_file.read_text())
        scenarios = raw if isinstance(raw, list) else raw.get("scenarios", raw)
        want = {s["id"]: hashlib.sha256("\n".join(s["assertions"]).encode()).hexdigest()[:12]
                for s in scenarios}

        checked, stale = 0, []
        for g in runs_root.glob("*/*/run-*/grading.json"):
            scenario = g.parts[-4]
            if scenario not in want:
                continue
            checked += 1
            have = json.loads(g.read_text()).get("assertions_sha")
            if have != want[scenario]:
                stale.append(f"{g.relative_to(runs_root)}: has {have}, current {want[scenario]}")

        self.assertTrue(checked, "no gradings compared, is this probe reading the right tree?")
        self.assertEqual(
            stale, [],
            f"{len(stale)} grading(s) scored against an older checklist; re-grade them:\n  "
            + "\n  ".join(stale[:8]) + ("\n  ..." if len(stale) > 8 else ""))

    def test_prose_percentage_pairs_exist_in_the_data(self):
        """Every "**N% → M%**" in the README must be a real cell or model row.

        The prose quotes per-scenario figures (`ops` on Haiku 4.5, 29% → 92%) alongside
        model-level ones. An earlier probe tried to bind those to whichever model name sat
        nearest in the sentence and matched across a comma, pairing Fable's prose with
        Opus's numbers. Position in a sentence is not a reliable key.

        So this checks the weaker but honest property: the pair must appear *somewhere* in
        the aggregate. That catches a stale or invented figure, which is the actual failure
        mode, twice now, without pretending to know which cell a sentence meant.
        """
        if not self.AGG.exists():
            self.skipTest("no aggregate committed")
        data = json.loads(self.AGG.read_text())
        # Both files, because CHANGELOG.md states its figures in prose rather than a table
        # and the table-shaped check above cannot see them. It kept a 52-cell tally for the
        # four Claude columns long after the matrix grew to 77 across six runtimes, and no
        # device noticed. A number needs a guard wherever it is published.
        readme = "\n".join((REPO / f).read_text() for f in ("README.md", "CHANGELOG.md"))

        real = set()
        for cells in data["scenarios"].values():
            for cell, v in cells.items():
                base = cells.get(cell.replace("_with_skill", "_baseline"))
                skill = cells.get(cell.replace("_baseline", "_with_skill"))
                if base and skill:
                    # Accept both roundings. Prose quotes a cell either way, "83% → 100%"
                    # in a table, "83.3% → 100.0%" in a sentence, and a probe that only
                    # knew one of them reported a correctly-sourced figure as invented.
                    for places in (0, 1):
                        real.add((round(base["pass_rate"] * 100, places) if places else
                                  round(base["pass_rate"] * 100),
                                  round(skill["pass_rate"] * 100, places) if places else
                                  round(skill["pass_rate"] * 100)))
        for v in data["by_model"].values():
            real.add((round(v["baseline"]["pass_rate"] * 100),
                      round(v["with_skill"]["pass_rate"] * 100)))
            real.add((round(v["baseline"]["pass_rate"] * 100, 1),
                      round(v["with_skill"]["pass_rate"] * 100, 1)))

        # Match arrow pairs whether or not they are bold. The first version required `**`
        # around them, so a figure written in plain parentheses, "(83.3% → 100.0%)", was
        # never checked at all. Swapping it for an invented number kept the suite green,
        # which is the failure this whole class of test exists to prevent.
        # Skip lines reporting the routing eval: rank-1 and top-3 percentages come from
        # trigger_eval.py, not from the benchmark, so they are correctly absent here. The
        # first version of this check flagged "Rank-1 went 80% -> 100%" as an invented
        # benchmark figure, which would have taught a reader to ignore it.
        lines = [ln for ln in readme.splitlines()
                 if not re.search(r"rank-?1|top-?3|routing|trigger", ln, re.I)]
        pairs = [(float(a), float(b)) for a, b in
                 re.findall(r"([\d.]+)% → ([\d.]+)%", "\n".join(lines))]
        self.assertTrue(pairs, "no arrow-form figures in README, is the probe broken?")
        orphans = [p for p in pairs if p not in real]
        self.assertEqual(orphans, [], f"a published figure is absent from benchmark.json: {orphans}")

    def test_incomplete_provenance_is_disclosed(self):
        """If the stored runs cannot be tied to the current prompts, the README must say so.

        A pass rate reads as a measurement. It stays one only while the reader can tell what
        it measured, and the committed runs predate the harness's prompt hash, so they
        cannot be tied to today's scenario prompts. That is a fine state to be in and a bad
        state to be quiet about.
        """
        if not self.AGG.exists():
            self.skipTest("no aggregate committed")
        pv = json.loads(self.AGG.read_text()).get("provenance")
        self.assertIsNotNone(pv, "aggregate records no provenance, regenerate it")
        if pv["runs"] and pv["prompt_verified"] < pv["runs"]:
            readme = (REPO / "README.md").read_text().lower()
            self.assertTrue(
                "prompt-hash" in readme or "prompt hash" in readme or "predate" in readme,
                f"only {pv['prompt_verified']}/{pv['runs']} runs are tied to the current "
                "prompts, and the README does not say so")

    def test_run_count_matches(self):
        if not self.AGG.exists():
            self.skipTest("no aggregate committed")
        data = json.loads(self.AGG.read_text())
        total = sum(cell.get("n", 0)
                    for scen in data["scenarios"].values() for cell in scen.values())
        readme = (REPO / "README.md").read_text()
        m = re.search(r"\*\*(\d+) blind-graded runs", readme)
        self.assertIsNotNone(m, "README no longer states a run count")
        self.assertEqual(int(m.group(1)), total,
                         f"README claims {m.group(1)} runs, aggregate holds {total}")


class TestDocumentationLinks(unittest.TestCase):
    """Cross-document links rot silently when a heading is reworded.

    Renaming `## Codex` to `## Codex, Copilot CLI, Gemini CLI` in the install guide left the
    README's badge pointing at `#codex`, which GitHub renders as a link that simply lands at
    the top of the page. Nothing errors; the reader just does not get where they were going.
    """

    DOCS = [REPO / "README.md", REPO / "docs" / "install.md", REPO / "RELEASING.md",
            REPO / "CLAUDE.md", REPO / "CONTRIBUTING.md"]

    @staticmethod
    def _anchors(path: Path) -> set:
        return {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-")
                for h in re.findall(r"^##+ (.+)$", path.read_text(), re.M)}

    def test_referenced_images_exist(self):
        """A broken image renders as a grey placeholder icon and nothing errors.

        The link checker above only follows `.md` targets, so the README's header banner: the first thing anyone sees, had no check behind it at all. Covers both Markdown
        image syntax and the raw <img> tags used for centring.
        """
        pattern = re.compile(r'!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]+src="([^"]+)"')
        checked = 0
        for doc in self.DOCS:
            if not doc.exists():
                continue
            for md, html in pattern.findall(doc.read_text()):
                src = md or html
                if src.startswith(("http://", "https://", "data:")):
                    continue          # external images are the link checker's problem
                target = (doc.parent / src).resolve()
                self.assertTrue(target.exists(),
                                f"{doc.relative_to(REPO)} shows an image at {src}, "
                                "which does not exist. It renders as a broken placeholder")
                self.assertGreater(target.stat().st_size, 0,
                                   f"{doc.relative_to(REPO)} shows {src}, which is empty")
                checked += 1
        self.assertGreater(checked, 0, "found no images, is the probe broken?")

    def test_relative_links_resolve(self):
        checked = 0
        for doc in self.DOCS:
            if not doc.exists():
                continue
            for target, frag in re.findall(r"\]\(([A-Za-z0-9._/-]+\.md)(#[a-z0-9-]*)?\)",
                                           doc.read_text()):
                dest = (doc.parent / target).resolve()
                self.assertTrue(dest.exists(),
                                f"{doc.name} links to {target}, which does not exist")
                if frag:
                    self.assertIn(frag[1:], self._anchors(dest),
                                  f"{doc.name} links to {target}{frag}, but {dest.name} has "
                                  "no heading with that anchor")
                checked += 1
        self.assertGreater(checked, 5, "found almost no links, is the probe broken?")


class TestAgentContextFiles(unittest.TestCase):
    """One real file, the rest point at it. Copies drift; pointers cannot."""

    def test_agents_md_is_the_cross_runtime_entry_point(self):
        self.assertTrue((REPO / "AGENTS.md").exists())
        self.assertTrue((REPO / "CLAUDE.md").exists())

    def test_context_files_are_pointers_not_copies(self):
        """Anything beyond the one canonical file must be short enough that it is obviously
        a pointer. A second full copy is how the two fall out of step."""
        canonical = (REPO / "CLAUDE.md").read_text()
        for name in ["GEMINI.md", "QWEN.md", ".clinerules", ".windsurfrules",
                     ".junie/guidelines.md", ".github/copilot-instructions.md",
                     ".cursor/rules/poka-yoke.mdc"]:
            p = REPO / name
            if not p.exists():
                continue
            body = p.read_text()
            self.assertNotEqual(canonical, body, f"{name} is a full copy of CLAUDE.md")
            self.assertLess(len(body.splitlines()), 20,
                            f"{name} is long enough to have become a second source of truth")


if __name__ == "__main__":
    unittest.main(verbosity=2)
