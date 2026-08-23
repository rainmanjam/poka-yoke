#!/usr/bin/env python3
"""Routing precision check, which of the 11 skills gets picked?

The description optimizer tests one skill in isolation: does it fire or not. That cannot
detect the failure this plugin is most exposed to, eleven skills with overlapping
descriptions competing for the same query, so the *wrong* one loads. A skill that fires
reliably and routes wrongly scores perfectly on a trigger eval and still fails the user.

This shows every skill's name and description, exactly as Claude sees them in
available_skills, and asks which single one applies. One call per query.

    python3 benchmarks/routing_check.py
    python3 benchmarks/routing_check.py --model claude-haiku-4-5-20251001
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "plugins/poka-yoke/skills"

# (query, expected skill). Each is phrased the way someone would actually ask, without
# naming the mode, if the description only works when the user says the mode's name,
# it is not doing its job.
CASES = [
    ("can you look through src/billing/ and tell me what's easy to get wrong in there before we ship", "audit"),
    ("what should the types look like for a subscription that can be trialing, active, past due or cancelled", "design"),
    ("the team agreed to run the formatter before committing and half of them still don't, i've asked twice", "guardrails"),
    ("we double charged 340 customers last night, refunded everyone, want to be sure it can't happen again", "retro"),
    ("users keep deleting their workspaces by accident then emailing support in a panic", "ux"),
    ("this PR drops the legacy_email column and updates the code that reads it, can i deploy it friday afternoon", "ops"),
    ("our revenue dashboard was wrong for three weeks, an upstream rename made the join return nulls", "data"),
    ("i'm worried we've missed a tenant filter somewhere and one customer can see another's documents", "authz"),
    ("our support bot extracts a refund amount from the chat message and calls the refund API, sometimes it refunds twice", "llm"),
    ("claude keeps force pushing even though CLAUDE.md says never to, in caps, twice", "agent-guardrails"),
    ("what is poka-yoke and how would it apply to a typescript codebase", "poka-yoke"),
    # Deliberate near-misses between modes that share vocabulary.
    ("add a pre-commit hook so secrets can't get committed", "guardrails"),
    ("stop the agent from running terraform apply", "agent-guardrails"),
    ("our AI feature sometimes returns malformed JSON that breaks the parser downstream", "llm"),
    ("make it impossible to write a query that isn't scoped to the current tenant", "authz"),
]

PROMPT = """You are Claude Code deciding which skill to load for a user's message.

AVAILABLE SKILLS:
{skills}

USER MESSAGE:
{query}

Which single skill should load? Reply with ONLY the skill name, exactly as listed above.
If none apply, reply NONE."""


def load_skills() -> dict[str, str]:
    out = {}
    for p in sorted(SKILLS.glob("*/SKILL.md")):
        fm = p.read_text().split("---")[1]
        name = re.search(r"^name:\s*(.+)$", fm, re.M).group(1).strip()
        desc = re.search(r"^description:\s*>-?\s*\n((?:\s{2,}.*\n)+)", fm, re.M)
        desc = " ".join(desc.group(1).split()) if desc else ""
        out[name] = desc
    return out


def ask(query: str, listing: str, model: str) -> str:
    r = subprocess.run(
        ["claude", "-p", PROMPT.format(skills=listing, query=query), "--model", model],
        capture_output=True, text=True, timeout=300,
        env={**os.environ, "SSH_AUTH_SOCK": ""})
    return (r.stdout or "").strip().split("\n")[-1].strip().strip("`* ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="opus")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--truncate", type=int, metavar="N",
                    help="cut each description to N chars first. Claude Code shortens the "
                         "skill listing to fit a character budget when many skills are "
                         "installed, so a description whose trigger words sit past the cut "
                         "never gets matched. This simulates that.")
    a = ap.parse_args()

    skills = load_skills()
    if a.truncate:
        skills = {n: (d[:a.truncate] + "…" if len(d) > a.truncate else d)
                  for n, d in skills.items()}
        lost = sum(1 for d in skills.values() if '"' not in d)
        print(f"truncated to {a.truncate} chars, {lost}/{len(skills)} skills lost "
              f"all quoted trigger phrases")
    listing = "\n".join(f"- {n}: {d}" for n, d in skills.items())
    print(f"{len(skills)} skills, {len(CASES)} routing cases, model {a.model}\n")

    with ThreadPoolExecutor(a.workers) as ex:
        got = list(ex.map(lambda c: ask(c[0], listing, a.model), CASES))

    hits, confusion = 0, Counter()
    for (q, want), g in zip(CASES, got):
        ok = g == want
        hits += ok
        print(f"  {'ok  ' if ok else 'MISS'}  want {want:28} got {g:28} {q[:44]}")
        if not ok:
            confusion[f"{want} -> {g}"] += 1

    print(f"\nrouting accuracy: {hits}/{len(CASES)} ({100*hits/len(CASES):.0f}%)")
    if confusion:
        print("\nconfusions (these are the descriptions to disambiguate):")
        for k, v in confusion.most_common():
            print(f"  {v}x  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
