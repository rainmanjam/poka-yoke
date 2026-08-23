#!/usr/bin/env python3
"""Fable orchestrates Opus + Sonnet over every published markdown file, hunting conflicts.

    python3 scripts/review_md_conflicts.py --dry-run   # what it would cost
    python3 scripts/review_md_conflicts.py             # run it
    python3 scripts/review_md_conflicts.py --units entry data

Why this exists rather than one more read-through: the docs changed a great deal in a short
time: the benchmark went from 240 runs on four Claude models to 591 across six runtimes, two
support tiers moved, two badges appeared, and a normalized-gain figure was corrected twice.
Every one of those touched several files, and a number that agrees with itself inside one
document can still contradict another.

Two reviewers per unit, on different models, because a single reader tends to accept whatever
frame the document sets. Fable adjudicates rather than concatenating: a finding both models
raise is worth more than two lists stapled together.

Reviewers are told to verify external facts with a web search. Today produced enough
plausible-and-wrong claims that "it sounds right" is not a standard.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fanout import REPO, OPUS, SONNET, FABLE, Task, run_one, extract_json   # noqa: E402

UNITS: dict[str, list[str]] = {
    "entry":     ["README.md"],
    "bench":     ["benchmarks/README.md", "docs/benchmark-comparison.md"],
    "install":   ["docs/install.md", "plugins/poka-yoke/README.md"],
    "process":   ["CONTRIBUTING.md", "RELEASING.md", "CHANGELOG.md", "SECURITY.md"],
    "method":    ["docs/method.md", "plugins/poka-yoke/references/hazard-catalog.md"],
    "agents":    ["CLAUDE.md", "docs/poka-yoke/registry.md"],
}

SCHEMA = {
    "file": "docs/install.md",
    "quote": "the exact sentence you object to, copied verbatim so it can be found",
    "kind": "conflict | stale | unverifiable | wrong | gap",
    "severity": "high | medium | low",
    "problem": "one sentence, stated so a reader could check it",
    "conflicts_with": "file + quote it contradicts, or '' if this is not a conflict",
    "suggested": "the replacement text, or the specific change to make",
    "checked": "how you verified it: a file you read, or a search you ran and what it said",
}

BRIEF = """You are reviewing the published documentation of `poka-yoke`, an open-source
Claude Code plugin, immediately after a large round of changes. Your job is to find places
where the documents now disagree with each other, with the code, or with reality.

Read these files IN FULL, from {repo}:
{files}

You must also read, as ground truth for every benchmark number:
  {repo}/benchmarks/results/benchmark.json   (generated; the aggregate)
  {repo}/benchmarks/results/benchmark.md     (generated; the report)

What to look for, in priority order:

1. CONFLICT: two documents stating different things. Run counts, model names, pass rates,
   scenario counts, support tiers, badge claims, install commands. The recent changes moved
   the benchmark from 4 Claude models to 6 runtimes, promoted two runtimes between support
   tiers, and corrected a normalized-gain figure twice. Check every number against
   benchmark.json rather than against another document.
2. STALE: a claim that was true before those changes and is not now.
3. WRONG: a factual error about the outside world. Cite Shigeo Shingo, poka-yoke's origin,
   Toyota, the cost-of-defects literature, YouTube or GitHub mechanics, licence terms, or any
   named third-party tool or company. VERIFY THESE WITH A WEB SEARCH. Do not rely on memory;
   several claims in this repository were confidently wrong until checked.
4. UNVERIFIABLE: a claim a reader could not check, stated as if they could.
5. GAP, something a reader needs that is missing.

Rules:
- Quote verbatim. A finding nobody can locate is not a finding.
- Do not report style, tone, or wording preferences. Only defects.
- Zero findings for a clean unit is a correct and valued answer. Do not invent to fill space.
- If you searched to verify something, say what the search returned in `checked`.

Return ONLY a JSON array. Each element:
{schema}
"""

ADJUDICATE = """Two reviewers on different models read the same documentation unit and each
returned findings. Merge them into one ranked list.

Rules:
- A finding BOTH raised is stronger evidence than either alone. Say so in `agreement`.
- Drop anything you judge to be taste rather than a defect, or that you cannot locate in the
  quoted file. Say what you dropped and why, in a `dropped` array.
- Where they disagree about a fact, prefer the one that shows its verification in `checked`.
- Do not invent findings neither reviewer raised.

Reviewer A (opus):
{a}

Reviewer B (sonnet):
{b}

Return ONLY a JSON object: {{"findings": [...], "dropped": [...]}} where each finding keeps
the original fields plus "agreement": "both" | "opus" | "sonnet".
"""


def build(unit: str) -> str:
    files = "\n".join(f"  {REPO}/{f}" for f in UNITS[unit])
    return BRIEF.format(repo=REPO, files=files, schema=json.dumps(SCHEMA, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", nargs="+", default=list(UNITS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="private/md-conflicts.md")
    a = ap.parse_args()

    units = [u for u in a.units if u in UNITS]
    print(f"== {len(units)} units x 2 reviewers + {len(units)} adjudications "
          f"= {len(units)*3} calls ==")
    for u in units:
        print(f"   {u:<10} {', '.join(UNITS[u])}")
    if a.dry_run:
        return 0

    results = {}
    for u in units:
        prompt = build(u)
        per = {}
        for rev in (OPUS, SONNET):
            out, err = run_one(rev, prompt)
            if err:
                print(f"   FAIL {u}/{rev.name}: {err}", flush=True)
                per[rev.name] = []
                continue
            data, perr = extract_json(out)
            if perr:
                print(f"   FAIL {u}/{rev.name}: {perr}", flush=True)
                per[rev.name] = []
                continue
            per[rev.name] = data if isinstance(data, list) else [data]
            print(f"   ok   {u}/{rev.name}: {len(per[rev.name])} findings", flush=True)

        merged, err = extract_json(run_one(FABLE, ADJUDICATE.format(
            a=json.dumps(per.get("opus", []), indent=2),
            b=json.dumps(per.get("sonnet", []), indent=2)))[0])
        if err or not isinstance(merged, dict):
            print(f"   FAIL {u}/fable: {err or 'unexpected shape'}", flush=True)
            merged = {"findings": per.get("opus", []) + per.get("sonnet", []), "dropped": []}
        results[u] = merged
        print(f"   ok   {u}/fable: {len(merged.get('findings', []))} kept, "
              f"{len(merged.get('dropped', []))} dropped", flush=True)

    out = Path(REPO) / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, dropped = [], []
    for u, m in results.items():
        for f in m.get("findings", []):
            f["unit"] = u
            rows.append(f)
        dropped += [{**d, "unit": u} if isinstance(d, dict) else {"unit": u, "why": str(d)}
                    for d in m.get("dropped", [])]
    order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda r: (order.get(str(r.get("severity")).lower(), 3),
                             r.get("agreement") != "both"))

    L = ["# Documentation conflict review", "",
         f"Fable adjudicating Opus and Sonnet over {len(units)} units, "
         f"{len(rows)} findings kept, {len(dropped)} dropped.", "",
         "Reviewers were told to verify external facts with a web search and to record what "
         "the search returned. A finding both models raised is marked `both`.", "",
         "| # | Sev | Agree | File | Problem | Suggested change |",
         "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        cell = lambda k: str(r.get(k, "")).replace("|", "\\|").replace("\n", " ")[:220]
        L.append(f"| {i} | {cell('severity')} | {r.get('agreement','')} | "
                 f"`{cell('file')}` | {cell('problem')} | {cell('suggested')} |")
    L += ["", "## Detail", ""]
    for i, r in enumerate(rows, 1):
        L += [f"### {i}. {r.get('file','?')}, {r.get('kind','?')} ({r.get('severity','?')})", "",
              f"> {str(r.get('quote','')).strip()}", "",
              f"- **Problem**: {r.get('problem','')}",
              f"- **Conflicts with**: {r.get('conflicts_with') or ', '}",
              f"- **Suggested**: {r.get('suggested','')}",
              f"- **Verified how**: {r.get('checked',', ')}",
              f"- **Raised by**: {r.get('agreement','?')}", ""]
    if dropped:
        L += ["## Dropped by the adjudicator", ""]
        L += [f"- `{d.get('unit','')}`, {str(d.get('why') or d.get('problem') or d)[:200]}"
              for d in dropped]
    out.write_text("\n".join(L) + "\n")
    print(f"\nwrote {out}  ({len(rows)} findings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
