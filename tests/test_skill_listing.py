#!/usr/bin/env python3
"""Tests for the skill listing: the frontmatter that decides whether a skill triggers.

Two devices live here, both guarding things that were fixed by hand once and would
otherwise drift back:

  1. Description length. Claude Code shortens descriptions to fit the listing's
     character budget when many skills are installed. Our trigger phrases used to sit
     at 71-77% through descriptions averaging 789 characters, so a truncating listing
     cut them off entirely. They were rewritten to a 379 median. Nothing but this test
     stops the next edit from writing a 900-character description and quietly putting
     a skill back behind the cut.

  2. README coverage. The README's "Reach for it when" table is written by hand, so
     adding or renaming a skill silently leaves it under-reported. That is the
     fixed-value question, can an incomplete set pass?, asked of our own docs.

Run: python3 tests/test_skill_listing.py
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "plugins" / "poka-yoke" / "skills"
README = REPO / "README.md"

# A ceiling, not a target. The corpus median is ~396 and ours is ~379; this fails on a
# regression into truncation territory, not on a reasonable 420-character rewrite. A
# check that fires on healthy edits gets deleted, and then it guards nothing.
MAX_DESCRIPTION = 500


def frontmatter(path: Path) -> dict[str, str]:
    """Parse the subset of YAML our frontmatter uses: plain scalars and `>-` folded blocks.

    Deliberately not PyYAML: every other script here is standard library only, so the
    plugin has no dependency supply chain, and CI installs nothing to run this.
    """
    parts = path.read_text().split("---")
    if len(parts) < 3:
        raise AssertionError(f"{path}: no frontmatter block")
    out, key = {}, None
    for line in parts[1].splitlines():
        m = re.match(r"^([a-z][a-z-]*): *(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            out[key] = "" if val in (">-", "|", ">") else val
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def skills() -> list[tuple[str, dict[str, str]]]:
    return [(p.parent.name, frontmatter(p)) for p in sorted(SKILLS.glob("*/SKILL.md"))]


def readme_table_skills() -> set[str]:
    """The skill names in the README's 'Reach for it when' table, as `| **`name`** |` rows."""
    return set(re.findall(r"^\|\s*\*\*`([a-z0-9-]+)`\*\*\s*\|", README.read_text(), re.M))


class TestDescriptionFitsTheListing(unittest.TestCase):
    def test_every_description_is_under_the_ceiling(self):
        for name, fm in skills():
            with self.subTest(skill=name):
                n = len(fm.get("description", ""))
                self.assertLessEqual(
                    n, MAX_DESCRIPTION,
                    f"{name}: description is {n} chars (ceiling {MAX_DESCRIPTION}). "
                    f"Long descriptions get truncated in the listing and lose their "
                    f"trigger phrases, put detail in the skill body instead.")

    def test_every_description_is_non_trivial(self):
        # The other direction: an empty or stub description never matches anything.
        for name, fm in skills():
            with self.subTest(skill=name):
                self.assertGreater(len(fm.get("description", "")), 80,
                                   f"{name}: description too short to route on")

    def test_no_markdown_emphasis_in_descriptions(self):
        # The listing is plain text, so `*word*` renders as literal asterisks and wastes
        # budget. Underscores inside identifiers (org_id) are fine and intentional.
        for name, fm in skills():
            with self.subTest(skill=name):
                self.assertNotRegex(
                    fm.get("description", ""), r"\*",
                    f"{name}: markdown emphasis in description. It is not rendered")


class TestReadmeCoversEverySkill(unittest.TestCase):
    def test_table_matches_the_shipped_skills(self):
        shipped = {name for name, _ in skills()}
        documented = readme_table_skills()
        self.assertEqual(
            shipped, documented,
            f"README table and shipped skills disagree. "
            f"Missing from README: {sorted(shipped - documented) or 'none'}. "
            f"In README but not shipped: {sorted(documented - shipped) or 'none'}.")

    def test_table_was_actually_found(self):
        # Guards the guard: if the table's formatting changes, the regex above silently
        # matches nothing and the comparison passes for the wrong reason.
        self.assertGreater(len(readme_table_skills()), 5,
                           "parsed fewer than 6 rows: the README table format changed "
                           "and this check stopped seeing it")


if __name__ == "__main__":
    unittest.main(verbosity=2)
