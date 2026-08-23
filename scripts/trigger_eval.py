#!/usr/bin/env python3
"""Measure whether each skill's description carries the words users actually say.

The README is honest that these skills do not reliably auto-trigger. That was an observation
nobody could act on, because there was no number attached to it, description edits were made
on instinct and their effect was invisible.

This is a deterministic, offline approximation of routing: stemmed TF-IDF over the eleven
descriptions, scoring each fixture prompt. It cannot judge meaning, and it is not trying to;
it catches the two failure modes that actually dominate:

  * a description missing the vocabulary of its own canonical request (false negative), and
  * a description broad enough to outrank the skill that should have won (false positive).

A failure here almost always means fix the description, not the test.

Borrowed, with thanks, from the Tier-2 approach in addyosmani/agent-skills.

    python3 scripts/trigger_eval.py
    python3 scripts/trigger_eval.py --min-rank1 80     # CI ratchet
    python3 scripts/trigger_eval.py --explain guardrails
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "plugins" / "poka-yoke" / "skills"
CASES = REPO / "benchmarks" / "trigger-cases.json"

# Words that appear in nearly every description and carry no routing signal.
STOP = set("""a an the and or of to for in on with is are be it its this that you your we our
when use uses used using not no if then than as at by from so can could should there their
what which who how why any all each per into out over under about""".split())

COLLISION = 0.5     # cosine between two descriptions; above this they compete for prompts


def stem(w: str) -> str:
    """Deliberately crude. `guardrail`/`guardrails`, `deploy`/`deploying` should collapse;
    anything cleverer needs a dependency, and this file is standard library on purpose."""
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def toks(s: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z][a-z0-9-]+", s.lower()) if w not in STOP]


def descriptions() -> dict[str, str]:
    out = {}
    for d in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        t = (d / "SKILL.md").read_text()
        m = (re.search(r"^description:\s*>-?\s*\n((?:[ \t]+.*\n)+)", t, re.M)
             or re.search(r"^description:\s*(.+)$", t, re.M))
        out[d.name] = " ".join(m.group(1).split()) if m else ""
    return out


class Corpus:
    def __init__(self, docs: dict[str, str]):
        self.tf = {k: collections.Counter(toks(v)) for k, v in docs.items()}
        df = collections.Counter(t for c in self.tf.values() for t in c)
        n = len(self.tf)
        self.idf = lambda t: math.log(1 + n / (1 + df.get(t, 0)))
        self.vec = {k: self._v(c) for k, c in self.tf.items()}

    def _v(self, c):
        return {t: f * self.idf(t) for t, f in c.items()}

    @staticmethod
    def cos(a, b):
        if not a or not b:
            return 0.0
        num = sum(v * b.get(k, 0.0) for k, v in a.items())
        den = (math.sqrt(sum(v * v for v in a.values()))
               * math.sqrt(sum(v * v for v in b.values())))
        return num / den if den else 0.0

    def rank(self, prompt: str):
        q = self._v(collections.Counter(toks(prompt)))
        return sorted(((self.cos(q, v), k) for k, v in self.vec.items()), reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-rank1", type=float, default=None,
                    help="fail below this rank-1 percentage")
    ap.add_argument("--explain", metavar="SKILL",
                    help="show which terms carry a skill, and what beats it")
    a = ap.parse_args()

    docs = descriptions()
    if not docs:
        print("no skills found: the probe is broken, not the skills", file=sys.stderr)
        return 2
    corpus = Corpus(docs)
    data = json.loads(CASES.read_text())
    cases = data["cases"] if isinstance(data, dict) else data

    if a.explain:
        if a.explain not in docs:
            print(f"unknown skill {a.explain!r}", file=sys.stderr); return 2
        top = sorted(corpus.vec[a.explain].items(), key=lambda kv: -kv[1])[:12]
        print(f"  {a.explain}, heaviest terms:")
        print("    " + ", ".join(f"{t}({w:.1f})" for t, w in top))
        for c in cases:
            if c.get("expect") == a.explain:
                r = corpus.rank(c["prompt"])
                print(f"\n  prompt: {c['prompt'][:88]}")
                for s, k in r[:4]:
                    print(f"    {s:.3f}  {k}{'   <-- wanted' if k == a.explain else ''}")
        return 0

    pos = [c for c in cases if c.get("kind") == "positive" and c.get("expect")]
    neg = [c for c in cases if c.get("kind") == "negative"]

    print(f"  {len(docs)} skills · {len(pos)} positive · {len(neg)} negative prompts\n")
    r1 = r3 = 0
    misses = []
    for c in pos:
        r = corpus.rank(c["prompt"])
        top = [k for _, k in r[:3]]
        hit1, hit3 = top[0] == c["expect"], c["expect"] in top
        r1 += hit1; r3 += hit3
        mark = "#1  " if hit1 else ("top3" if hit3 else "MISS")
        print(f"    {c['expect']:17} -> {top[0]:17} {mark}  ({r[0][0]:.3f})")
        if not hit1:
            misses.append((c["expect"], top[0], c["prompt"]))

    pct1 = 100 * r1 / len(pos)
    print(f"\n    rank-1 {r1}/{len(pos)} ({pct1:.0f}%)   top-3 {r3}/{len(pos)} "
          f"({100*r3/len(pos):.0f}%)")

    # Separation: if an ordinary dev task outscores a real one, no threshold can divide them.
    weakest_pos = min(corpus.rank(c["prompt"])[0][0] for c in pos)
    strongest_neg = max(corpus.rank(c["prompt"])[0][0] for c in neg) if neg else 0.0
    print(f"    weakest positive {weakest_pos:.3f}   strongest negative {strongest_neg:.3f}"
          f"   {'separated' if weakest_pos > strongest_neg else 'OVERLAPPING'}")
    if weakest_pos <= strongest_neg:
        # Reported, never enforced. The strongest false positive is "set up CI for this fresh
        # repo", which scores on `guardrails` because guardrails genuinely is about CI.
        # Driving that to zero means deleting "CI" from the description, which would break
        # the true positive. Lexical scoring cannot separate the two; a model reading the
        # whole description can. This line is here to stop anyone believing otherwise.
        print("      (expected: some ordinary requests share vocabulary with a real one , "
              " no threshold divides them, which is why this is not a gate)")

    ks = list(corpus.vec)
    coll = [(ks[i], ks[j], Corpus.cos(corpus.vec[ks[i]], corpus.vec[ks[j]]))
            for i in range(len(ks)) for j in range(i + 1, len(ks))
            if Corpus.cos(corpus.vec[ks[i]], corpus.vec[ks[j]]) > COLLISION]
    for x, y, c in coll:
        print(f"    collision: {x} <-> {y} ({c:.2f})")

    lens = {k: len(v) for k, v in docs.items()}
    print(f"    description length: median {sorted(lens.values())[len(lens)//2]} "
          f"max {max(lens.values())} ({max(lens, key=lens.get)})")

    if misses:
        print("\n  misses: the description lacks its own prompt's vocabulary:")
        for want, got, p in misses:
            print(f"    {want} lost to {got}: {p[:76]}")
        print(f"  `--explain {misses[0][0]}` shows which terms are missing.")

    if coll:
        print("\n  ✗ descriptions collide; they will compete for the same prompts",
              file=sys.stderr)
        return 1
    if a.min_rank1 is not None and pct1 < a.min_rank1:
        print(f"\n  ✗ rank-1 {pct1:.0f}% is below the floor of {a.min_rank1:.0f}%",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
