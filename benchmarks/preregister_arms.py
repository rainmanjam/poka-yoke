#!/usr/bin/env python3
"""Freeze the control arms before any of them are run.

A control arm you can edit after seeing the result is not a control. If the placebo loses by
more than expected there is a standing temptation to decide it was "too weak" and strengthen
it, and if it wins there is a temptation to decide it was "too strong". Neither edit feels
dishonest while you are making it, and nothing in the harness would notice either.

So: hash every file each arm's router can reach, record the hashes and the word counts, and
commit that before the sweep. `--check` then fails if anything moved. The registration also
records the size asymmetry between arms, which is the number a reader needs in order to
discount the comparison, and which is easier to leave out of a write-up than to falsify.

    preregister_arms.py            # write the registration
    preregister_arms.py --check    # fail if any arm's content changed since

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "benchmarks" / "arms.lock.json"

ARM_ROOTS = {
    "with_skill":     REPO / "plugins/poka-yoke",
    "with_placebo":   REPO / "benchmarks/controls/clean-code",
    "with_defensive": REPO / "benchmarks/controls/defensive",
}


def _fingerprint(root: pathlib.Path) -> dict:
    """Hash and measure every markdown file under an arm.

    Everything under the root counts, not just the router: the preamble tells the model to
    follow routing into sub-skills and to read whatever references those point at, so a
    reference file is as much a part of the treatment as the router is. Hashing only the
    entry point would let the actual content change while the lock stayed green.
    """
    files = sorted(p for p in root.rglob("*.md") if p.is_file())
    if not files:
        raise SystemExit(f"✗ no markdown under {root}. An arm with no content is not an arm.")
    entries, total_words = {}, 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        words = len(text.split())
        total_words += words
        entries[str(f.relative_to(REPO))] = {
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "words": words,
        }
    return {"files": entries, "file_count": len(files), "total_words": total_words}


# Modes a scenario can route to. Per-route load is the honest denominator for the size
# asymmetry: a run reads the router plus ONE sub-skill, never the whole arm. Reporting total
# arm words instead made the controls look 87% smaller than the treatment when the load a
# model actually sees differs by about a fifth, which would have understated the controls in
# exactly the direction that flatters the treatment.
MODES = ["design", "audit", "retro", "ux", "authz", "data", "ops",
         "guardrails", "agent-guardrails", "llm"]


def _per_route(root: pathlib.Path, router: pathlib.Path) -> dict:
    """Words a single run loads: router + the one sub-skill it routes to."""
    base = len(router.read_text(encoding="utf-8").split()) if router.exists() else 0
    out = {}
    for mode in MODES:
        f = root / "skills" / mode / "SKILL.md"
        out[mode] = base + len(f.read_text(encoding="utf-8").split()) if f.exists() else None
    return out


ROUTERS = {
    "with_skill":     REPO / "plugins/poka-yoke/skills/poka-yoke/SKILL.md",
    "with_placebo":   REPO / "benchmarks/controls/clean-code/skills/clean-code/SKILL.md",
    "with_defensive": REPO / "benchmarks/controls/defensive/skills/defensive/SKILL.md",
}


def build() -> dict:
    arms = {name: _fingerprint(root) for name, root in ARM_ROOTS.items()}
    for name, a in arms.items():
        a["per_route_words"] = _per_route(ARM_ROOTS[name], ROUTERS[name])
    treat = arms["with_skill"]["per_route_words"]
    for name, a in arms.items():
        deltas = [round((a["per_route_words"][m] - treat[m]) * 100 / treat[m], 1)
                  for m in MODES
                  if a["per_route_words"].get(m) and treat.get(m)]
        a["per_route_vs_treatment_pct"] = deltas and round(sum(deltas) / len(deltas), 1) or None
        a["routes_authored"] = sum(1 for m in MODES if a["per_route_words"].get(m))
    return {
        "note": "Frozen before the sweep. Any change here invalidates comparisons made "
                "against the runs it produced.",
        "arms": arms,
    }


def cmd_write() -> int:
    reg = build()
    OUT.write_text(json.dumps(reg, indent=1, sort_keys=True) + "\n")
    print(f"✓ {OUT.relative_to(REPO)}")
    for name, a in sorted(reg["arms"].items()):
        pr = a["per_route_vs_treatment_pct"]
        pr_txt = f"{pr:+6.1f}%" if pr is not None else "     -"
        print(f"  {name:<16} {a['routes_authored']:2}/10 routes  "
              f"{a['total_words']:6} words total  per-route {pr_txt} vs treatment")
    print("\nCommit this before running the sweep. --check fails if any arm changes.")
    return 0


def cmd_check() -> int:
    if not OUT.exists():
        print(f"✗ {OUT.relative_to(REPO)} missing. Nothing was registered, so nothing can be "
              f"verified; run without --check first.", file=sys.stderr)
        return 2
    old = json.loads(OUT.read_text())["arms"]
    new = build()["arms"]
    problems = []
    for name in sorted(set(old) | set(new)):
        if name not in old:
            problems.append(f"{name}: arm added since registration")
            continue
        if name not in new:
            problems.append(f"{name}: arm removed since registration")
            continue
        o, n = old[name]["files"], new[name]["files"]
        for path in sorted(set(o) | set(n)):
            if path not in o:
                problems.append(f"{name}: {path} added")
            elif path not in n:
                problems.append(f"{name}: {path} deleted")
            elif o[path]["sha256"] != n[path]["sha256"]:
                problems.append(f"{name}: {path} edited "
                                f"({o[path]['words']} -> {n[path]['words']} words)")
    if problems:
        print("✗ arm content changed since registration:", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        print("\n  Any runs already graded were produced by different text. Either revert, or\n"
              "  re-register and discard those runs. Keeping both is how a tuned control gets\n"
              "  published as a pre-registered one.", file=sys.stderr)
        return 1
    n_files = sum(a["file_count"] for a in new.values())
    print(f"✓ all {len(new)} arms unchanged ({n_files} files)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="fail if any arm's content changed since registration")
    return cmd_check() if ap.parse_args().check else cmd_write()


if __name__ == "__main__":
    sys.exit(main())
