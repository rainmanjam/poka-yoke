#!/usr/bin/env python3
"""Every linter rule the docs name must actually exist in that linter.

The skills tell people to enable specific rules, `ruff DTZ003`, `clippy::unwrap_used`,
`@typescript-eslint/no-floating-promises`. Those names are the most perishable thing in this
repository: linters rename, deprecate and reorganise rules, and nothing here would notice.
A skill that confidently recommends a rule that no longer exists is giving bad advice with
full confidence, which is precisely the rung-zero failure this project argues against. It
relies on remembered knowledge.

So ask the linters. `ruff rule --all` enumerates them; clippy answers per lint; eslint and
golangci-lint can list what they ship. This is a Control: the tool itself decides, and there
is nothing to remember.

    python3 scripts/check_cited_rules.py                    # verify what is installed
    python3 scripts/check_cited_rules.py --list             # just show what is cited
    python3 scripts/check_cited_rules.py --require ruff     # absence of ruff is a failure

Exit codes: 0 clean · 1 a cited rule does not exist · 2 nothing could be verified at all.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "poka-yoke"

# Where a rule name can legitimately appear. Anything else is prose about linting in
# general, not a recommendation someone will act on.
MD_SOURCES = [
    PLUGIN / "references",
    PLUGIN / "skills",
    PLUGIN / "assets" / "devices",
    ROOT / "docs",
]
PY_SOURCE = PLUGIN / "scripts" / "detect_hazards.py"

# `ruff F632` and the hazard IDs `F2`/`C1`/`X5` share a shape. Three or more digits is what
# separates a linter code from a catalog ID, and every real ruff code has at least three.
RUFF = re.compile(r"\b([A-Z]{1,4}\d{3,4})\b")
CLIPPY = re.compile(r"\bclippy::([a-z][a-z_]*)\b")
TSESLINT = re.compile(r"@typescript-eslint/([a-z][a-z-]*)")
ESLINT = re.compile(r"\beslint[ -]([a-z][a-z0-9-]*(?:/[a-z0-9-]+)?)\b")
GOLANGCI = re.compile(r"\bgolangci-lint\s+([a-z][a-z0-9-]*)\b")

# Words that follow a linter's name in ordinary prose. Without these the extractor reports
# `golangci-lint to ...` as a missing rule, and a checker that cries wolf gets switched off.
STOPWORDS = {
    "to", "and", "or", "for", "with", "the", "a", "an", "in", "on", "is", "are", "will",
    "can", "does", "has", "have", "run", "runs", "enable", "enables", "disable", "config",
    "configs", "rules", "rule", "plugin", "plugins", "which", "that", "this", "already",
    "actually", "here", "instead", "rather", "does-not-exist",
}


def cited() -> dict[str, set[str]]:
    """Collect rule names by ecosystem, from Markdown and from the detector's own table."""
    out: dict[str, set[str]] = defaultdict(set)

    # The detector's COVERED_BY maps a hazard to the linter that does it better. Parsing it
    # structurally rather than by regex means the citations are read exactly as written.
    tree = ast.parse(PY_SOURCE.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                _scan(v.value, out)

    # Generated reports quote the problems they found, so scanning one would report every bad
    # rule name twice: once where it lives and once where it was written up. They now live in
    # private/, outside the roots below, but the guard stays. It costs nothing and the next
    # report to land in docs/ will be caught by it rather than by a confusing double count.
    GENERATED = {"copy-review.md", "outreach.md"}
    for src in MD_SOURCES:
        for f in sorted(src.rglob("*.md")) if src.is_dir() else [src]:
            if f.name in GENERATED:
                continue
            text = f.read_text()
            # In prose, only backticked spans are recommendations; the rest is discussion.
            for span in re.findall(r"`([^`\n]+)`", text):
                _scan(span, out)
            # Config blocks name rules as JSON keys, which are already quoted, not ticked.
            for span in re.findall(r'"([^"\n]+)"\s*:', text):
                _scan(span, out)
            # And in a clippy.toml / Cargo.toml lint table they appear bare, on the left of
            # an assignment, with no `clippy::` prefix to recognise them by. Only inside a
            # fenced block, so ordinary prose containing `x = "warn"` is not mined for lints.
            for block in re.findall(r"```(?:toml|ini)?\n(.*?)```", text, re.S):
                for name in re.findall(r'^\s*([a-z][a-z_]{4,})\s*=\s*"(?:warn|deny|allow)"',
                                       block, re.M):
                    out["clippy"].add(name)
    return out


def _scan(s: str, out: dict[str, set[str]]) -> None:
    for m in TSESLINT.findall(s):
        out["typescript-eslint"].add(m)
    for m in CLIPPY.findall(s):
        out["clippy"].add(m)
    # Strip the ts-eslint hits so their trailing rule name is not re-read as a core rule.
    bare = TSESLINT.sub("", s)
    for m in ESLINT.findall(bare):
        if m in STOPWORDS:
            continue
        # `eslint jest/no-focused-tests` is conventional shorthand: the rule ships in
        # eslint-plugin-jest, not in eslint itself. Attributing it to core made the checker
        # report a correct citation as missing, which is how a checker earns its way into
        # being ignored.
        if "/" in m:
            plugin, rule = m.split("/", 1)
            out[f"eslint-plugin-{plugin}"].add(rule)
        else:
            out["eslint"].add(m)
    for m in GOLANGCI.findall(bare):
        if m not in STOPWORDS:
            out["golangci-lint"].add(m)
    for m in RUFF.findall(bare):
        out["ruff"].add(m)


# --------------------------------------------------------------------------- verifiers
# Each returns (known_rules, None) or (None, reason-it-could-not-run).

def verify_ruff():
    if not shutil.which("ruff"):
        return None, "ruff is not installed"
    r = subprocess.run(["ruff", "rule", "--all", "--output-format", "json"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, f"`ruff rule --all` failed: {r.stderr.strip()[:80]}"
    return {d["code"] for d in json.loads(r.stdout)}, None


def verify_clippy(names):
    """clippy only registers its lints while driving a compile, so probe one at a time.
    There are two cited rules; the cost is irrelevant and the answer is authoritative."""
    if not shutil.which("clippy-driver"):
        return None, "clippy-driver is not installed"
    known = set()
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "probe.rs"
        probe.write_text("fn main(){}\n")
        for n in sorted(names):
            r = subprocess.run(
                ["clippy-driver", "--edition", "2021", f"-Wclippy::{n}",
                 "--emit=metadata", "-o", str(Path(td) / "out"), str(probe)],
                capture_output=True, text=True)
            out = (r.stderr + r.stdout).lower()
            # A RENAMED lint still compiles. It merely warns. Treating "not unknown" as
            # "fine" let `clippy::integer_arithmetic` sit in the docs after it became
            # `clippy::arithmetic_side_effects`: the checker ran, passed, and measured
            # nothing. Deprecated is the same story.
            if "unknown lint" in out or "has been renamed" in out or "deprecated" in out:
                continue
            known.add(n)
    return known, None


def _node_rules(expr: str, what: str):
    if not shutil.which("node"):
        return None, "node is not installed"
    r = subprocess.run(["node", "-e", expr], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        return None, f"{what} is not installed here (node could not load it)"
    return set(json.loads(r.stdout)), None


def verify_eslint():
    return _node_rules(
        "const {builtinRules}=require('eslint/use-at-your-own-risk');"
        "console.log(JSON.stringify([...builtinRules.keys()]))", "eslint")


def verify_tseslint():
    return _node_rules(
        "const p=require('@typescript-eslint/eslint-plugin');"
        "console.log(JSON.stringify(Object.keys(p.rules)))", "@typescript-eslint")


def verify_eslint_plugin(plugin: str):
    """Third-party eslint plugins expose their rules the same way ts-eslint does."""
    return _node_rules(
        f"const p=require('eslint-plugin-{plugin}');"
        "console.log(JSON.stringify(Object.keys(p.rules)))", f"eslint-plugin-{plugin}")


def verify_golangci():
    if not shutil.which("golangci-lint"):
        return None, "golangci-lint is not installed"
    r = subprocess.run(["golangci-lint", "linters"], capture_output=True, text=True)
    if r.returncode != 0:
        # Say what it said. "`golangci-lint linters` failed" sent one CI run chasing a
        # missing install when the real message was a Go version mismatch, printed by the
        # tool and thrown away here.
        why = (r.stderr or r.stdout or "").strip().splitlines()
        return None, f"`golangci-lint linters` failed: {why[0][:120] if why else 'no output'}"
    return set(re.findall(r"^(\w[\w-]*)", r.stdout, re.M)), None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print what is cited, verify nothing")
    ap.add_argument("--require", default="",
                    help="comma-separated ecosystems whose absence is a failure (CI uses this)")
    a = ap.parse_args()

    found = cited()
    if not found:
        print("Found no cited rules at all: the extractor is broken, not the docs.",
              file=sys.stderr)
        return 2

    if a.list:
        for eco in sorted(found):
            print(f"{eco} ({len(found[eco])})")
            for n in sorted(found[eco]):
                print(f"  {n}")
        return 0

    required = {s.strip() for s in a.require.split(",") if s.strip()}
    verifiers = {
        "ruff": verify_ruff,
        "clippy": lambda: verify_clippy(found["clippy"]),
        "eslint": verify_eslint,
        "typescript-eslint": verify_tseslint,
        "golangci-lint": verify_golangci,
    }
    for eco in found:
        if eco.startswith("eslint-plugin-"):
            verifiers.setdefault(eco, (lambda p: lambda: verify_eslint_plugin(p))(eco[14:]))

    bad, skipped, checked = [], [], 0
    for eco in sorted(found):
        names = found[eco]
        v = verifiers.get(eco)
        if v is None:
            skipped.append(f"{eco}: no verifier"); continue
        known, why = v()
        if known is None:
            if eco in required:
                print(f"::error::{eco} was required but could not be checked, {why}",
                      file=sys.stderr)
                return 2
            skipped.append(f"{eco}: {why} ({len(names)} rule(s) unchecked)")
            continue
        checked += len(names)
        unknown = sorted(n for n in names if n not in known)
        status = "✓" if not unknown else "✗"
        print(f"  {status} {eco:20} {len(names) - len(unknown)}/{len(names)} verified")
        bad += [f"{eco}: `{n}` does not exist" for n in unknown]

    for s in skipped:
        print(f"  · skipped {s}")

    # An empty sweep must not look like a pass. This project has shipped that bug twice.
    if checked == 0:
        print("\nVerified nothing: no linter was available. This is not an all-clear.",
              file=sys.stderr)
        return 2

    if bad:
        print(f"\n{len(bad)} cited rule(s) do not exist:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 1

    print(f"\n✓ {checked} cited rule(s) verified against the linters that own them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
