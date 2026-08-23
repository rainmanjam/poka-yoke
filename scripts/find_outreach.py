#!/usr/bin/env python3
"""Find places where poka-yoke genuinely belongs, and track what was submitted where.

Three models search independently across different channel types; Fable reconciles them into
one ranked, de-duplicated list; the result becomes `private/outreach.md`, which is a tracker
rather than a one-off report: the Status column is meant to be edited by hand as things are
submitted, accepted or rejected.

A deliberate constraint runs through the prompts: every target must be somewhere this project
would be *welcome*, with a submission process that exists and is followed. That is not
squeamishness. Lists and communities reject off-topic submissions, and a rejected PR on a
popular list is a public record of having spammed it. The approach that respects the
maintainer is also the approach that works.

    python3 scripts/find_outreach.py --dry-run
    python3 scripts/find_outreach.py
    python3 scripts/find_outreach.py --channels awesome-lists registries
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fanout import PANEL, REPO, Task, budget_guard, fan_out, synthesise  # noqa: E402

PITCH = """
The project is **poka-yoke** (https://github.com/rainmanjam/poka-yoke), currently private,
about to be published alongside a YouTube video.

What it is: a plugin of 11 skills that apply Shigeo Shingo's mistake-proofing method to
software, auditing code for hazards, designing APIs that cannot be misused, installing
guardrails, turning incidents into devices. It ships a dependency-free static analyser (42
pattern rules over 19 hazard shapes for TypeScript, Python, Go, Rust and SQL), installable
pre-commit / GitHub Actions / lint templates, and PreToolUse hooks for AI coding agents.

Distinguishing facts, for judging where it fits:
- Runs on 16 agent runtimes (Claude Code, Codex, Cursor, Gemini CLI, Devin, Kimi, Hermes,
  Copilot, Windsurf, Cline, Zed, Aider and others) from one set of skills.
- Benchmarked: 240 blind-graded runs across four models, baseline vs with-skill.
- Zero dependencies. MIT licensed.
- Sits at the intersection of: AI coding agents, static analysis, code quality, developer
  experience, lean/TPS methodology, and defensive API design.
"""

RULES = """
Hard constraints on what you may propose. A target only qualifies if ALL of these hold:

1. The project would be genuinely ON TOPIC there. Not "tangentially relevant": a maintainer
   reading the submission should think "yes, that belongs on this list".
2. There is a real, documented submission route: a CONTRIBUTING file, a submission form, an
   issue template, a "submit your project" page. Name it and link it.
3. The venue is ALIVE. Cite evidence: a recent commit, a recent accepted submission, recent
   posts. A list last touched in 2019 is worthless.
4. The submission would be a single, specific, honest contribution.

Do NOT propose any of the following, and do not try to reframe them:
- Opening pull requests on unrelated repositories to get attention.
- Mass or templated submissions across many venues.
- Comments on issues or discussions where the project is not the subject.
- Anything involving multiple accounts, upvote coordination, or undisclosed promotion.
- Paid placement dressed as community contribution.

If you cannot find enough qualifying targets in your channel, return fewer. A short list of
real fits is the deliverable; padding it with weak ones makes the whole list untrustworthy.
"""

SCHEMA = """
Reply with ONLY a JSON array. No prose outside it.

[
  {
    "name": "awesome-static-analysis",
    "url": "https://github.com/analysis-tools-dev/static-analysis",
    "channel": "awesome-lists",
    "what_to_submit": "specific: which section, what the one-line entry would say",
    "submission_route": "https://.../CONTRIBUTING.md - PR adding a line to the Multiple-languages section",
    "evidence_alive": "last commit 2026-08, ~40 PRs merged in the last 90 days",
    "audience_fit": "why THIS project belongs to THAT audience, one or two sentences",
    "reach": "high | medium | low",
    "effort": "low | medium | high",
    "risk": "anything that could make this land badly, or 'none'",
    "verified": true
  }
]

Set "verified": false for anything you could not actually check, and say so in "evidence_alive".
An unverified guess labelled as verified is worse than no entry: it costs someone a wasted
submission and their credibility.
"""

CHANNELS = {
    "awesome-lists": "Curated `awesome-*` GitHub lists that accept new entries: static "
                     "analysis, code quality, developer tools, AI coding agents, LLM tooling, "
                     "lean/DevOps practice. Find the specific list AND the specific section.",
    "registries": "Plugin and extension registries, marketplaces and directories: Claude Code "
                  "plugin marketplaces, MCP server registries, Codex/Cursor/Zed extension "
                  "directories, VS Code marketplace equivalents, and any agent-skill indexes.",
    "communities": "Communities where a post about this would be on-topic and welcomed rather "
                   "than tolerated: subreddits, forums, Discords/Slacks, Hacker News, "
                   "Lobsters. State the specific posting rules that apply.",
    "publications": "Sites and newsletters that accept technical submissions or pitches: "
                    "dev.to, Hashnode, InfoQ, developer newsletters, podcasts taking guests. "
                    "Name the submission process.",
    "adjacent-projects": "Projects whose own documentation legitimately lists related tools "
                         ",  lint rule collections, agent-skill collections, TPS/lean software "
                         "resources, where an addition would be a normal contribution.",
}


def verify_urls(records, workers: int = 12) -> None:
    """Fetch every proposed URL and staple the real status onto the entry.

    The first run asked the adjudicator to drop targets whose URLs "looked invented". Every
    one it dropped on that basis turned out to return 200, thin evidence and fabrication are
    indistinguishable by eye, so the judgement discarded ten working venues. Existence is a
    fact you can check in a hundred milliseconds; nobody should be guessing at it.
    """
    import time
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor

    seen: dict[str, str] = {}

    # A live site behind bot protection answers 403 or 429, and a rate limit is a statement
    # about our request rate, not about whether the venue exists. Treating those as dead
    # would rebuild the very failure this replaced, dropping real targets, with a script
    # instead of a model doing the dropping.
    REACHABLE = {"200", "403", "429", "401", "405"}

    def status(url: str) -> str:
        if url in seen:
            return seen[url]
        code = "?"
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0 poka-yoke"})
                code = str(urllib.request.urlopen(req, timeout=15).status)
                break
            except Exception as e:                  # noqa: BLE001 - any failure is a result
                code = str(getattr(e, "code", type(e).__name__))
                if code == "429" and attempt < 2:
                    time.sleep(2 + 3 * attempt)     # back off, then believe the answer
                    continue
                break
        seen[url] = code
        return code

    urls = [f.get("url") for r in records for f in r["findings"]
            if isinstance(f, dict) and f.get("url")]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(status, set(urls)))
    live = 0
    for r in records:
        for f in r["findings"]:
            if isinstance(f, dict) and f.get("url"):
                f["http_status"] = seen.get(f["url"], "?")
                live += f["http_status"] in REACHABLE
    print(f"  checked {len(set(urls))} distinct URL(s); {live}/{len(urls)} entries reachable")


def build_tasks(names: list[str]) -> list[Task]:
    return [Task(
        key=c,
        instruction=(
            "You are finding places where an open-source project could be legitimately "
            "submitted or contributed, to reach the developers who would benefit from it.\n"
            f"{PITCH}\n"
            f"YOUR CHANNEL FOR THIS SEARCH, cover only this one, thoroughly:\n{CHANNELS[c]}\n"
            "\nUse whatever web search or browsing tools you have to check that each target "
            "exists, is active, and accepts submissions. If you have no web access, say so in "
            "every entry's evidence_alive field and set verified to false.\n"
            f"{RULES}\n{SCHEMA}"),
    ) for c in names]


ADJUDICATE = """
Three models searched independently for places an open-source project could be submitted.
Reconcile their results into one ranked list.

- Merge duplicates (the same venue found by more than one model) and record who found it in
  "found_by". Prefer the entry with the most specific submission route.
- DROP anything that fails the constraints the searchers were given: no unrelated-repo PRs,
  no mass submissions, no off-topic posting, nothing requiring undisclosed promotion.
- Do NOT judge whether a URL is real. Every URL has already been fetched and its HTTP status
  is attached to the entry as `http_status`. Drop entries whose status is 404 or an error;
  keep the rest. Judging plausibility by eye discarded ten working venues on the first run,
  because a searcher writing thin evidence looks identical to a searcher inventing one.
- Rank by reach-per-unit-effort, best first, with unverified entries below verified ones.
- Keep at most 30. Say in "dropped_note" how many you dropped and why.

Reply with ONLY a JSON object:
{
  "targets": [ { ...same fields as the input, plus "found_by": ["opus","agy"] } ],
  "dropped_note": "..."
}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channels", nargs="+", choices=sorted(CHANNELS), default=sorted(CHANNELS))
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--max-calls", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reuse", action="store_true",
                    help="re-adjudicate the last search instead of running it again")
    ap.add_argument("--out", default="private/outreach.md")
    a = ap.parse_args()

    tasks = build_tasks(a.channels)
    print(f"== outreach search: {len(tasks)} channel(s), {len(PANEL)} searchers + 1 adjudicator ==")
    n_calls = 1 if a.reuse else len(tasks) * len(PANEL) + 1
    if budget_guard(n_calls, a.max_calls, a.dry_run):
        return 0

    work = REPO / ".outreach-work"
    if a.reuse:
        cached = work / "records.json"
        if not cached.exists():
            print("no previous search to reuse", file=sys.stderr); return 2
        records = json.loads(cached.read_text())
        print(f"  reusing {len(records)} cached search result(s): no searches re-run")
    else:
        records = fan_out(tasks, workers=a.workers, workdir=work)
    verify_urls(records)
    ok = [r for r in records if not r["error"]]
    if not ok:
        print("\nEvery searcher failed. This is not 'no targets found'.", file=sys.stderr)
        for r in records:
            print(f"  {r['task']}/{r['reviewer']}: {r['error']}", file=sys.stderr)
        return 2

    raw_n = sum(len(r["findings"]) for r in ok)
    print(f"\n  {len(ok)}/{len(records)} searches succeeded, {raw_n} raw target(s)")

    merged, raw, err = synthesise(ADJUDICATE, records, workdir=work)
    work.mkdir(parents=True, exist_ok=True)
    (work / "records.json").write_text(json.dumps(records, indent=2))
    if err or not merged:
        print(f"\nAdjudication failed ({err}); raw results kept in "
              f"{work.relative_to(REPO)}/records.json", file=sys.stderr)
        return 1

    targets = merged.get("targets", merged if isinstance(merged, list) else [])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = REPO / a.out
    out.parent.mkdir(parents=True, exist_ok=True)

    L = [
        "# Outreach tracker", "",
        f"Candidate venues for sharing poka-yoke, found {stamp} by "
        "`scripts/find_outreach.py` (Opus, Antigravity and Codex searching independently; "
        "Fable reconciling).", "",
        "## How to use this", "",
        "**The URL column is a fetched HTTP status, not an opinion.** Every link here was "
        "requested; 403 and 429 mean the site is alive and declining to talk to a script. "
        "Everything else in a row. That the venue accepts submissions, that the route named "
        "is the right one, is still a model's claim. Open the link and read the "
        "contribution rules before acting on any row.", "",
        "The first run asked the adjudicator to drop targets whose URLs *looked* invented. "
        "Every one it dropped that way returned 200. Thin evidence and fabrication are "
        "indistinguishable by eye, so existence is checked now and never judged.", "",
        "Edit the Status column by hand as things move. The generator never rewrites this "
        "file in place; re-running it writes a fresh file, so copy your statuses across or "
        "point `--out` somewhere else.", "",
        "Ground rules, which are also what makes submissions land:", "",
        "- One venue, one honest submission. No templated blasts.",
        "- Read the contribution guide first and follow its format exactly.",
        "- Disclose that you are the author.",
        "- If a venue says no, that is the end of it there.", "",
        "## Targets", "",
        "| # | Venue | Channel | Reach | Effort | URL | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, t in enumerate(targets, 1):
        nm = str(t.get("name", "?")).replace("|", "\\|")
        url = t.get("url", "")
        link = f"[{nm}]({url})" if url else nm
        L.append(f"| {i} | {link} | {t.get('channel','?')} | {t.get('reach','?')} | "
                 f"{t.get('effort','?')} | {t.get('http_status','?')} | "
                 f"not started |")
    L += ["", "---", "", "## Detail", ""]
    for i, t in enumerate(targets, 1):
        L += [f"### {i}. {t.get('name','?')}", "",
              f"- **URL**: {t.get('url',', ')}",
              f"- **Channel**: {t.get('channel','?')} · found by "
              f"{', '.join(t.get('found_by', [])) or '?'}",
              f"- **What to submit**: {t.get('what_to_submit',', ')}",
              f"- **Submission route**: {t.get('submission_route',', ')}",
              f"- **Evidence it is active**: {t.get('evidence_alive',', ')}",
              f"- **Audience fit**: {t.get('audience_fit',', ')}",
              f"- **Risk**: {t.get('risk',', ')}",
              f"- **Verified by the searcher**: {'yes' if t.get('verified') else 'NO, check before acting'}",
              ""]
    if merged.get("dropped_note"):
        L += ["---", "", "## What was dropped", "", merged["dropped_note"], ""]
    out.write_text("\n".join(L) + "\n")
    print(f"\n✓ {len(targets)} target(s) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
