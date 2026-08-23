#!/usr/bin/env python3
"""Review every word of published documentation, using three models and a fourth to judge.

Mechanical checks already cover what is checkable: paths resolve, counts match, links point
somewhere, cited linter rules exist. What they cannot see is a sentence that is confident and
wrong. `Shigeo Shingo built the Toyota Production System's quality method` passed every test
in this repository and was still false, he was an outside consultant who formalised
poka-yoke, and the system was Ohno's and Toyoda's. Nothing but reading catches that.

So: three models read the copy, Fable reconciles what they say, and a human verifies what
survives before any of it is acted on.

    python3 scripts/review_copy.py --dry-run     # what it would cost
    python3 scripts/review_copy.py               # run it
    python3 scripts/review_copy.py --units entry method
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fanout import PANEL, REPO, Task, budget_guard, fan_out, synthesise  # noqa: E402

# Grouped by the job each document does, not by directory: a reviewer judging the entry point
# needs different instincts from one reading a reference table, and mixing them produces
# notes that are true of neither.
UNITS: dict[str, list[str]] = {
    "entry":      ["README.md"],
    "install":    ["docs/install.md", "plugins/poka-yoke/README.md"],
    "method":     ["docs/method.md", "plugins/poka-yoke/references/hazard-catalog.md"],
    "process":    ["CONTRIBUTING.md", "SECURITY.md", "RELEASING.md",
                   "CODE_OF_CONDUCT.md", "CHANGELOG.md", "CLAUDE.md"],
    "skills-core": ["plugins/poka-yoke/skills/poka-yoke/SKILL.md",
                    "plugins/poka-yoke/skills/audit/SKILL.md",
                    "plugins/poka-yoke/skills/design/SKILL.md",
                    "plugins/poka-yoke/skills/guardrails/SKILL.md",
                    "plugins/poka-yoke/skills/retro/SKILL.md"],
    "skills-domain": ["plugins/poka-yoke/skills/ux/SKILL.md",
                      "plugins/poka-yoke/skills/ops/SKILL.md",
                      "plugins/poka-yoke/skills/data/SKILL.md",
                      "plugins/poka-yoke/skills/authz/SKILL.md",
                      "plugins/poka-yoke/skills/llm/SKILL.md",
                      "plugins/poka-yoke/skills/agent-guardrails/SKILL.md"],
    "references": ["plugins/poka-yoke/references/lang-typescript.md",
                   "plugins/poka-yoke/references/lang-python.md",
                   "plugins/poka-yoke/references/lang-rust-go.md",
                   "plugins/poka-yoke/references/ux-patterns.md"],
    "supporting": ["benchmarks/README.md",
                   "plugins/poka-yoke/assets/devices/claude-hooks/README.md",
                   "plugins/poka-yoke/assets/devices/lint/README.md",
                   "docs/benchmark-comparison.md"],
}

LENSES = """
1. OVERSTATED OR UNVERIFIABLE CLAIMS: the highest-value lens. Any sentence asserting a fact
   about history, a person, a tool, a number, or what some other system does, which a
   knowledgeable reader could challenge. Attribution errors especially: who actually did the
   thing being described. Flag anything that sounds authoritative but is not supported.

2. PROSE QUALITY AND VOICE. These documents were written across many sessions. Look for
   drift in register, sentences that restate the previous one, hedging, filler, and passages
   where the rhythm collapses. Name the specific sentence, not the general feeling.

3. AUDIENCE FIT, many readers will arrive from a YouTube video knowing nothing. Does the
   document make its value obvious before it explains its theory? Flag where a newcomer
   would stall, and where jargon appears before it is earned.

4. ACCURACY AGAINST THE CODE: the repository is readable from where you are running. Where
   a document describes what the code does, check it. Flag disagreements with file paths,
   command names, counts, or behaviour.
"""

SCHEMA = """
Reply with ONLY a JSON array. No preamble, no explanation outside the JSON.

[
  {
    "file": "README.md",
    "quote": "the exact text you are objecting to, copied verbatim so it can be located",
    "lens": "claim | prose | audience | accuracy",
    "severity": "high | medium | low",
    "problem": "what is wrong, in one or two sentences",
    "suggestion": "concrete replacement text, or the specific change to make"
  }
]

Rules that matter:
- `quote` MUST be copied exactly from the file. It is how the finding gets verified. A
  paraphrase makes the finding unusable.
- Report only what you would defend to the author. A long list of vague notes is worse than
  three specific ones, because it costs the reader more to triage than it returns.
- If a document is genuinely fine, return [].
- Do not propose rewriting the voice of the whole document. Flag sentences.
"""

ADJUDICATE = """
Three different models reviewed the same documentation independently. Reconcile their
findings into one ranked list.

Your job:
- Merge findings that are the same objection worded differently. Record how many of the
  three raised it in "raised_by".
- Drop findings that are matters of taste dressed as defects, and findings whose `quote`
  looks paraphrased rather than copied.
- A finding raised by only ONE reviewer is not automatically weak. The single most serious
  error ever found in this repository: a wrong attribution about Shigeo Shingo, is exactly
  the kind only one careful reader spots. Judge it on whether the objection holds, never on
  the vote count.
- Rank by what would most damage a knowledgeable reader's trust, highest first.

Reply with ONLY a JSON array:
[
  {
    "file": "...", "quote": "...", "lens": "...", "severity": "high|medium|low",
    "raised_by": ["opus","codex"], "problem": "...", "suggestion": "...",
    "why_it_matters": "one sentence on the cost of leaving it"
  }
]
"""


def build_tasks(names: list[str]) -> list[Task]:
    tasks = []
    for unit in names:
        paths = UNITS[unit]
        body, missing = [], []
        for rel in paths:
            p = REPO / rel
            if not p.exists():
                missing.append(rel); continue
            body.append(f"\n\n===== FILE: {rel} =====\n\n{p.read_text()}")
        if missing:
            print(f"  ! {unit}: missing {missing}", file=sys.stderr)
        if not body:
            continue
        tasks.append(Task(
            key=unit,
            instruction=(
                "You are reviewing published documentation for a software project called "
                "poka-yoke, before it is shown to a wide audience. The repository root is "
                f"{REPO} and you may read any file in it to check claims.\n"
                "Review the copy through these four lenses:\n" + LENSES + "\n" + SCHEMA),
            body="".join(body),
            body_name=f"{unit}.md"))
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--units", nargs="+", choices=sorted(UNITS), default=sorted(UNITS))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-calls", type=int, default=40, help="HARD ceiling across all vendors")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="private/copy-review.md")
    a = ap.parse_args()

    tasks = build_tasks(a.units)
    if not tasks:
        print("no units resolved to any files, nothing to review", file=sys.stderr)
        return 2

    words = sum(len(t.body.split()) for t in tasks)
    print(f"== copy review: {len(tasks)} unit(s), {words:,} words, "
          f"{len(PANEL)} reviewers + 1 adjudicator ==")
    if budget_guard(len(tasks) * len(PANEL) + 1, a.max_calls, a.dry_run):
        return 0

    work = REPO / ".review-work"
    records = fan_out(tasks, workers=a.workers, workdir=work)

    ok = [r for r in records if not r["error"]]
    if not ok:
        print("\nEvery reviewer failed. This is not a clean bill of health.", file=sys.stderr)
        for r in records:
            print(f"  {r['task']}/{r['reviewer']}: {r['error']}", file=sys.stderr)
        return 2

    total = sum(len(r["findings"]) for r in ok)
    print(f"\n  {len(ok)}/{len(records)} reviewer runs succeeded, {total} raw finding(s)")

    merged, raw, err = synthesise(ADJUDICATE, records, workdir=work)
    if err or merged is None:
        print(f"\nAdjudication failed ({err}). Raw findings are in {work}/records.json",
              file=sys.stderr)
        (work / "records.json").write_text(json.dumps(records, indent=2))
        return 1

    out = REPO / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Copy review", "",
        f"Generated {stamp} by `scripts/review_copy.py`.", "",
        f"{len(PANEL)} models reviewed {len(tasks)} unit(s) of documentation "
        f"({words:,} words) independently; Fable reconciled the results.", "",
        "**Nothing here is a verified defect.** Each finding still has to be checked against "
        "the file before it is acted on: the `quote` field is there so it can be located.", "",
        f"| # | file | lens | severity | raised by | problem |", "|---|---|---|---|---|---|",
    ]
    for i, f in enumerate(merged, 1):
        rb = ", ".join(f.get("raised_by", [])) or "?"
        prob = str(f.get("problem", "")).replace("|", "\\|")[:150]
        lines.append(f"| {i} | `{f.get('file','?')}` | {f.get('lens','?')} | "
                     f"{f.get('severity','?')} | {rb} | {prob} |")
    lines += ["", "---", ""]
    for i, f in enumerate(merged, 1):
        lines += [f"## {i}. {f.get('file','?')}, {f.get('severity','?')}", "",
                  f"> {str(f.get('quote','')).strip()}", "",
                  f"**Problem** ({f.get('lens','?')}, raised by "
                  f"{', '.join(f.get('raised_by', [])) or '?'}): {f.get('problem','')}", "",
                  f"**Suggestion**: {f.get('suggestion','')}", ""]
        if f.get("why_it_matters"):
            lines += [f"**Why it matters**: {f['why_it_matters']}", ""]
    out.write_text("\n".join(lines) + "\n")
    (work / "records.json").write_text(json.dumps(records, indent=2))
    print(f"\n✓ {len(merged)} reconciled finding(s) -> {a.out}")
    print(f"  raw per-reviewer output kept in {work.relative_to(REPO)}/records.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
