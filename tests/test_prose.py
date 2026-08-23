#!/usr/bin/env python3
"""Prose checks for the published documentation.

Adapted from realrossmanngroup/no_ai_slop_writing_rules. Not every rule there is mechanical,
and not every rule there suits a technical README; what is checkable is checked here so it
cannot drift back in, and the rest stays a matter of judgement during review.

Why bother: this repository publishes a benchmark, its own regressions, and a list of the
times its instruments were wrong. Prose that reads as machine-generated undercuts all of it
before a reader reaches the numbers. Em-dash density in particular is a documented tell.

Run: python3 tests/test_prose.py
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Held as an escape, not as the character. A sweep that removed every em-dash from the
# repository rewrote this file too, turning `text.count("<em-dash>")` into `text.count(", ")`.
# The test then reported 235 em-dashes in a README that had none, and passed its own ban
# while measuring commas. A checker written in the thing it checks for will be edited by any
# tool that edits the thing.
EM_DASH = "\u2014"

DOCS = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "RELEASING.md",
        "benchmarks/README.md", "docs/install.md", "docs/method.md",
        "docs/benchmark-comparison.md", "plugins/poka-yoke/README.md"]

# Rule 4/11/15: words that stand in for evidence, hedge a claim into nothing, or pad.
BANNED = ["significantly", "dramatically", "extremely", "incredibly", "remarkably",
          "truly", "absolutely", "undoubtedly", "seamless", "robust", "comprehensive",
          "pivotal", "delve", "leverage", "utilize", "foster", "bolster", "underscore",
          "unveil", "streamline", "in today's world", "it's important to note",
          "when it comes to", "at the end of the day", "it goes without saying",
          "look no further", "may potentially", "can help to", "might be able to"]

# Rule 16: a heading names what the section holds; it does not tease or abstract.
VAGUE_HEADING = re.compile(
    r"^\s*#{2,4}\s+(broader|wider|larger|the hidden|what (this|it) means|"
    r"implications|industry-wide|final thoughts|key takeaways|going deeper|"
    r"the .*\btrap\b|why .*\b(matters|fails)\b)", re.I)


def prose_of(path: Path) -> str:
    """Documentation minus fenced code: a command is not prose and cannot be rewritten."""
    return re.sub(r"```.*?```", "", path.read_text(), flags=re.S)


class TestProse(unittest.TestCase):

    def test_no_banned_vocabulary(self):
        """An intensifier is a placeholder for the number it replaced."""
        found = []
        for d in DOCS:
            p = REPO / d
            if not p.exists():
                continue
            text = prose_of(p)
            for w in BANNED:
                for m in re.finditer(rf"\b{re.escape(w)}\b", text, re.I):
                    line = text[:m.start()].count("\n") + 1
                    found.append(f"{d}:{line} {m.group(0)!r}")
        self.assertEqual(found, [], "banned vocabulary:\n  " + "\n  ".join(found[:15]))

    def test_headings_name_their_contents(self):
        checked, bad = 0, []
        for d in DOCS:
            p = REPO / d
            if not p.exists():
                continue
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if re.match(r"^\s*#{2,4}\s+", line):
                    checked += 1
                    if VAGUE_HEADING.match(line):
                        bad.append(f"{d}:{i} {line.strip()!r}")
        self.assertTrue(checked, "no headings found, is the probe reading the right files?")
        self.assertEqual(bad, [], "headings that abstract rather than name:\n  " + "\n  ".join(bad))

    def test_em_dash_density_is_bounded(self):
        """Rule 1 bans the character outright. This repository does not: an em-dash earns
        its place in an aside that a comma would blur. What it cannot do is carry the
        structure of every other sentence, which is the shape a reader recognises as
        machine-written.

        So the check is a ceiling, not a ban: at most one per 120 words of prose. The
        published docs measured 250 in eleven files when this was written; the ceiling was
        set from where they landed after the ones doing no work were removed.
        """
        over = []
        for d in DOCS:
            p = REPO / d
            if not p.exists():
                continue
            text = prose_of(p)
            words = len(text.split())
            dashes = text.count(EM_DASH)
            if words < 200:
                continue
            per = words / dashes if dashes else float("inf")
            if per < 120:
                over.append(f"{d}: {dashes} em-dashes in {words} words "
                            f"(one per {per:.0f}; ceiling is one per 120)")
        self.assertEqual(over, [], "em-dash density:\n  " + "\n  ".join(over))


if __name__ == "__main__":
    unittest.main(verbosity=2)
