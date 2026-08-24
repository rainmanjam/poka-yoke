#!/usr/bin/env python3
"""Tests for the hazard detector.

Every rule needs a case both ways: a line that must match, and a near-miss that must not.
Precision matters more than recall here: a noisy rule trains people to ignore the whole
tool, which costs more than the hazards it finds. The near-miss cases are what keep it
honest, and they are the ones worth adding when you add a rule.

Run: python3 tests/test_detector.py
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DETECTOR = REPO / "plugins" / "poka-yoke" / "scripts" / "detect_hazards.py"
GUARD = (REPO / "plugins" / "poka-yoke" / "assets" / "devices" / "claude-hooks"
         / "guard_dangerous_commands.py")


def scan(filename: str, source: str, all_rules: bool = False) -> set[str]:
    """Scan a snippet and return the set of hazard IDs found.

    all_rules=True includes the rules a real linter does better, which are off by
    default: the detector's value is the ~19 checks nothing else performs, plus a
    pointer to the linter for the rest.
    """
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / filename
        p.write_text(source)
        cmd = [sys.executable, str(DETECTOR), "--paths", str(p), "--json"]
        if all_rules:
            cmd.append("--all")
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {f["id"] for f in json.loads(r.stdout)["findings"]}


def guard(tool: str, **tool_input) -> bool:
    """Return True if the guard hook denies this call."""
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input})
    r = subprocess.run([sys.executable, str(GUARD)], input=payload,
                       capture_output=True, text=True)
    return "deny" in r.stdout


def scan_all(filename: str, source: str) -> set[str]:
    return scan(filename, source, all_rules=True)


class TestDetects(unittest.TestCase):
    """The rules nothing else checks: the detector's actual value."""
    def test_adjacent_same_type_params(self):
        self.assertIn("C1", scan("a.py", "def transfer(src: str, dst: str) -> None: ...\n"))

    def test_boolean_flag_param(self):
        self.assertIn("C2", scan("a.ts", "function f(x: string, admin: boolean) {}\n"))

    def test_money_as_float(self):
        self.assertIn("C6", scan("a.py", "def f(amount: float): ...\n"))

    def test_unvalidated_json_parse(self):
        self.assertIn("C7", scan("a.ts", "const d = JSON.parse(body);\n"))

    def test_naive_datetime(self):
        self.assertIn("C9", scan_all("a.py", "now = datetime.utcnow()\n"))

    def test_unbounded_delete(self):
        self.assertIn("F2", scan("a.py", 'db.execute("DELETE FROM users")\n'))

    def test_destructive_ddl(self):
        self.assertIn("F2", scan("a.sql", "DROP TABLE accounts;\n"))

    def test_assert_as_validation(self):
        self.assertIn("F3", scan_all("a.py", "def f(x):\n    assert x > 0\n"))

    def test_two_phase_construction(self):
        self.assertIn("M1", scan("a.py", "def connect(self): ...\n"))

    def test_missing_idempotency_key(self):
        self.assertIn("M2", scan("a.py", "def charge(account, amount): ...\n"))

    def test_dangling_async_task(self):
        self.assertIn("M6", scan_all("a.py", "asyncio.create_task(send())\n"))

    def test_swallowed_error_ts(self):
        self.assertIn("X1", scan_all("a.ts", "try { f(); } catch (e) {}\n"))

    def test_bare_except(self):
        self.assertIn("X1", scan_all("a.py", "try:\n    f()\nexcept:\n    pass\n"))

    def test_discarded_go_error(self):
        self.assertIn("X1", scan_all("a.go", "x, _ := doThing()\n"))

    def test_focused_test(self):
        self.assertIn("X3", scan_all("a.ts", 'it.only("works", () => {});\n'))

    def test_explicit_any(self):
        self.assertIn("X4", scan_all("a.ts", "const x: any = 1;\n"))

    def test_mutable_default_arg(self):
        self.assertIn("X5", scan_all("a.py", "def f(items=[]): ...\n"))


class TestLinterCoveredRulesAreOptOut(unittest.TestCase):
    """Rules a real linter does better stay off by default, so the tool is a supplement
    rather than a worse reimplementation of ruff and eslint."""

    def test_bare_except_off_by_default(self):
        self.assertNotIn("X1", scan("a.py", "try:\n    f()\nexcept:\n    pass\n"))

    def test_mutable_default_off_by_default(self):
        self.assertNotIn("X5", scan("a.py", "def f(items=[]): ...\n"))

    def test_but_available_with_all(self):
        self.assertIn("X5", scan_all("a.py", "def f(items=[]): ...\n"))

    def test_novel_rules_still_on_by_default(self):
        # adjacent same-type params: nothing else checks this
        self.assertIn("C1", scan("a.py", "def transfer(src: str, dst: str) -> None: ...\n"))


class TestDoesNotFalselyFire(unittest.TestCase):
    """Near-misses. Each of these is a legitimate line a rule could plausibly over-match."""

    def test_different_types_not_flagged(self):
        self.assertNotIn("C1", scan("a.py", "def f(name: str, count: int) -> None: ...\n"))

    def test_bounded_delete_not_flagged(self):
        self.assertNotIn("F2", scan("a.py", 'db.execute("DELETE FROM users WHERE id = 1")\n'))

    def test_idempotent_charge_not_flagged(self):
        self.assertNotIn(
            "M2", scan("a.py", "def charge(account, amount, idempotency_key): ...\n"))

    def test_referenced_task_not_flagged(self):
        self.assertNotIn("M6", scan("a.py", "task = asyncio.create_task(send())\n"))

    def test_handled_exception_not_flagged(self):
        self.assertNotIn(
            "X1", scan("a.py", "try:\n    f()\nexcept ValueError:\n    raise\n"))

    def test_none_default_not_flagged(self):
        self.assertNotIn("X5", scan("a.py", "def f(items=None): ...\n"))

    def test_comment_only_line_not_flagged(self):
        self.assertEqual(set(), scan("a.py", "# def transfer(src: str, dst: str)\n"))


class TestEmptyScanIsNotAnAllClear(unittest.TestCase):
    """Zero findings from zero files used to look exactly like zero findings from a clean
    codebase. Found by running the detector across real repos: five reported 0 hazards and
    four of them contained no source files at all. A tool that cannot tell you it did
    nothing is worse than no tool, because it manufactures confidence."""

    def _run(self, *paths):
        cmd = [sys.executable, str(DETECTOR), "--paths", *paths, "--json"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout)

    def test_path_with_no_source_files_exits_nonzero(self):
        code, out = self._run(str(REPO / "README.md"))
        self.assertEqual(2, code, "scanning nothing must not exit 0 like a successful scan")
        self.assertEqual(0, out["files_scanned"])
        self.assertIn("NOT an all-clear", out["error"])

    def test_nonexistent_path_exits_nonzero(self):
        code, out = self._run(str(REPO / "no-such-directory"))
        self.assertEqual(2, code)
        self.assertEqual(0, out["files_scanned"])

    def test_real_scan_reports_how_many_files_it_read(self):
        code, out = self._run(str(DETECTOR))
        self.assertEqual(0, code)
        self.assertEqual(1, out["files_scanned"])

    def test_clean_scan_is_distinguishable_from_empty_scan(self):
        # The whole point: both report count 0, and files_scanned is what tells them apart.
        with tempfile.TemporaryDirectory() as td:
            clean = Path(td) / "clean.py"
            clean.write_text("x = 1\n")
            code, out = self._run(str(clean))
        self.assertEqual(0, code)
        self.assertEqual(0, out["count"])
        self.assertEqual(1, out["files_scanned"], "a clean file is a real scan, not an empty one")


class TestDocumentedCountsMatchTheRules(unittest.TestCase):
    """The README quotes how many rules and shapes the detector has.

    Both numbers were wrong at once: the docs said 19 shapes, and a reviewer checking them
    said 18. The real answer is 20, `RULES` holds 18, and C1 and F3 are implemented outside
    that table, so counting the table alone undercounts and nobody noticed either way.
    """

    def _detector(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dh", DETECTOR)
        m = importlib.util.module_from_spec(spec)
        sys.modules["dh"] = m
        spec.loader.exec_module(m)
        return m

    def test_readme_default_off_count_is_right(self):
        """How many rules are suppressed by default.

        Three different numbers were in circulation: the detector printed 20 (it was counting
        COVERED_BY *entries*, and one entry can suppress several per-language rules), a
        reviewer said 22, and the README said 20. The answer is 23, and the only way anyone
        was going to agree was to count the rules rather than the table describing them.
        """
        import re
        m = self._detector()
        suppressed = sum(1 for r in m.RULES if (r.id, r.name) in m.COVERED_BY)
        readme = (REPO / "README.md").read_text()
        # The claim moved from a prose sentence into the detector counts table when the
        # scanner was promoted to lead the README. This test failed loudly at that point
        # rather than silently passing, which is the behaviour intended: it asserts the claim
        # is present before checking it. The word form is still accepted because the table
        # spells the number out in its explanatory cell.
        words = {"Twenty": 20, "Twenty-one": 21, "Twenty-two": 22, "Twenty-three": 23,
                 "Twenty-four": 24, "Nineteen": 19}
        hit = re.search(r"(\w+(?:-\w+)?) of the rules are covered better by a real linter",
                        readme)
        self.assertIsNotNone(hit, "README no longer states the default-off count")
        self.assertIn(hit.group(1), words, f"unrecognised number word {hit.group(1)!r}")
        self.assertEqual(suppressed, words[hit.group(1)],
                         f"README says {hit.group(1)} ({words[hit.group(1)]}) rules are "
                         f"linter-covered; {suppressed} actually are")

    def test_readme_rule_and_shape_counts_are_right(self):
        import re
        m = self._detector()
        rules = len(m.RULES)
        ids = {r.id for r in m.RULES}
        # Rules implemented outside the pattern table still report a hazard ID.
        src = DETECTOR.read_text()
        ids |= set(re.findall(r'\bid="([A-Z]\d+)"', src)) | set(re.findall(r'"([CFMX]\d+)"', src))
        ids = {i for i in ids if re.fullmatch(r"[CFMX]\d+", i)}

        readme = (REPO / "README.md").read_text()
        # Both counts now live in the detector counts table rather than in one sentence.
        # This test remains the OWNER of what a "hazard shape" means: ids in RULES plus the
        # ids reported by the AST checks outside the pattern table (C1, F3). A second test
        # briefly recomputed that and got 18 against this test's 20, which would have let the
        # README satisfy one check while contradicting the other. One claim, one owner.
        shape_row = re.search(r"\| Shapes the detector reports \| \*\*(\d+)\*\* \|", readme)
        rule_row = re.search(r"\| Pattern rules \| \*\*(\d+)\*\* \|", readme)
        self.assertIsNotNone(shape_row, "README no longer states the hazard-shape count")
        self.assertIsNotNone(rule_row, "README no longer states the pattern-rule count")
        self.assertEqual(rules, int(rule_row.group(1)),
                         f"README says {rule_row.group(1)} rules, the detector has {rules}")
        self.assertEqual(len(ids), int(shape_row.group(1)),
                         f"README says {shape_row.group(1)} shapes, the detector reports "
                         f"{len(ids)}: {sorted(ids)}")


class TestSuggestHookRoutes(unittest.TestCase):
    """The README claims this hook "routes all ten modes correctly and stays silent on
    unrelated prompts". Nothing verified that until a reviewer pointed out the claim had no
    test behind it, which, by this repository's own argument, made it a hope.

    One match and one near-miss per mode: the near-misses are what stop the hook firing on
    every prompt that happens to contain the word "test" or "deploy".
    """

    SUGGEST = (REPO / "plugins" / "poka-yoke" / "assets" / "devices" / "claude-hooks"
               / "suggest_poka_yoke.py")

    MATCHES = {
        "audit":  "audit src/billing for anything that is easy to misuse",
        "design": "design the types for our subscription state machine so bad states cannot exist",
        "guardrails": "set up a pre-commit hook so unformatted code cannot get merged",
        "retro":  "we double charged customers after a queue redelivery, do a root cause",
        "ux":     "redesign our workspace deletion flow so users stop deleting things by accident",
        "ops":    "review this migration that drops a column before we deploy on friday",
        "data":   "go through our dbt models and find where a silent failure gives wrong numbers",
        "authz":  "check every query for a missing tenant filter, we are multi-tenant",
        "llm":    "our LLM feature returns unstructured output and the tool schema is loose",
        "agent-guardrails": "claude keeps editing files our CLAUDE.md says not to touch",
    }
    SILENT = [
        "what is the weather in paris",
        "rename this variable from foo to bar",
        "write a haiku about the sea",
        "what time is my meeting",
    ]

    def _run(self, prompt: str) -> str:
        r = subprocess.run([sys.executable, str(self.SUGGEST)],
                           input=json.dumps({"prompt": prompt}),
                           capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        return r.stdout.strip()

    def test_every_mode_is_reachable(self):
        for mode, prompt in self.MATCHES.items():
            out = self._run(prompt)
            self.assertTrue(out, f"{mode}: hook stayed silent on {prompt!r}")
            self.assertIn(f"`{mode}`", out,
                          f"{mode}: hook fired but named a different skill, {out[:120]}")

    def test_silent_on_unrelated_prompts(self):
        for prompt in self.SILENT:
            self.assertEqual("", self._run(prompt),
                             f"hook fired on an unrelated prompt: {prompt!r}")


class TestGuardHook(unittest.TestCase):
    def test_denies_force_push(self):
        self.assertTrue(guard("Bash", command="git push --force origin main"))

    def test_allows_force_with_lease(self):
        # The safe form must stay usable, or the device gets removed.
        self.assertFalse(guard("Bash", command="git push --force-with-lease origin feat"))

    def test_allows_ordinary_push(self):
        self.assertFalse(guard("Bash", command="git push origin main"))

    def test_denies_env_read(self):
        self.assertTrue(guard("Read", file_path="/app/.env"))

    def test_allows_env_example_read(self):
        self.assertFalse(guard("Read", file_path="/app/.env.example"))

    def test_denies_unbounded_delete(self):
        self.assertTrue(guard("Bash", command='psql -c "DELETE FROM users"'))

    def test_allows_bounded_delete(self):
        self.assertFalse(guard("Bash", command='psql -c "DELETE FROM users WHERE id=1"'))

    def test_denies_no_verify_commit(self):
        self.assertTrue(guard("Bash", command="git commit --no-verify -m wip"))

    def test_fails_open_on_malformed_input(self):
        # A hook that crashes blocks all tool use, which is its own outage.
        r = subprocess.run([sys.executable, str(GUARD)], input="not json",
                           capture_output=True, text=True)
        self.assertEqual(0, r.returncode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
