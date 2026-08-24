#!/usr/bin/env python3
"""Validate the grader against a human, and against a second model.

Everything already in place around grading controls BIAS: it is blind to configuration,
batched, scored against assertions written before the runs, and stamped with the checklist
hash so an edited checklist invalidates its own results. None of that establishes ACCURACY.
A grader can be perfectly unbiased and consistently wrong, and every number downstream
inherits the error without anything going red.

So this measures two different things and refuses to conflate them:

  * agreement with a HUMAN label      -> accuracy. The only ground truth available.
  * agreement with a SECOND MODEL     -> reliability. Cheap, automatable, and NOT accuracy:
                                         two models sharing a blind spot agree perfectly.

Three steps, in order:

    validate_grader.py --sample 60          # draw, write a blind worksheet
    validate_grader.py --second-grader M    # re-grade the same items with another model
    validate_grader.py --report             # agreement, broken out by original verdict

The worksheet deliberately shows the response and the assertion and NOTHING ELSE. Showing the
grader's verdict or its evidence would anchor the labeller onto the answer being tested, which
turns ground truth into a confirmation exercise.

Stdlib only, like the rest of the repo: this has to run wherever the harness runs.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import subprocess
import sys

# C5 from the bundled detector: a bare 300 does not say seconds.
SECOND_GRADER_TIMEOUT_S = 300

LIMIT = [0]          # set from --limit; a list so the command fn can read it
REPO = pathlib.Path(__file__).resolve().parent.parent
RUNS = REPO / "benchmarks" / "results" / "runs"
OUT = REPO / "benchmarks" / "results" / "validation"

# The six runtimes in the published aggregate. `results/runs/` also holds directories for
# models that have been superseded (claude-opus-4-5, claude-sonnet-4-5-...), which is 55% of
# the gradings on disk. Sampling those would validate a grader against runs nothing reports.
CURRENT = {
    "fable", "opus", "claude-sonnet-5", "claude-haiku-4-5-20251001",
    "codex-gpt-5.6-terra", "agy-gemini-3.1-pro",
}

SECOND_GRADER_PROMPT = """\
You are grading one assertion about one response. Answer only about the assertion given.

Do NOT run commands, read files, or search the repository. Everything needed is in this
message, and the response below is the only evidence. agy in plan mode tried to grep the repo
for the assertion text and its call was refused, which cost a verdict; a grader that goes
looking for outside evidence is also no longer grading the same thing the others graded.

ASSERTION:
{assertion}

RESPONSE:
{response}

Reply with exactly one JSON object and nothing else:
{{"passed": true or false, "evidence": "the quote or line that decides it, or why nothing does"}}
"""


# Arm suffixes, matched explicitly. The first version derived the config with
# `cell.rpartition("_")`, which splits on the LAST underscore: `claude-sonnet-5_baseline`
# parsed correctly, but `claude-sonnet-5_with_skill` became model `claude-sonnet-5_with` and
# config `skill`. That model name is not in CURRENT, so every treatment cell was silently
# dropped and the sampler drew 60 baseline items while printing a cheerful success line. All
# 97 with_skill cells were invisible, and the finding drawn from that sample ("disagreement
# concentrates on baseline runs") was an artifact of the bug rather than a fact about the
# grader. Match against the known set instead of inferring where the boundary is.
CONFIG_SUFFIXES = ("baseline", "with_skill", "with_placebo", "with_defensive")


def _split_cell(cell: str) -> tuple[str, str] | None:
    for cfg in CONFIG_SUFFIXES:
        if cell.endswith("_" + cfg):
            return cell[: -(len(cfg) + 1)], cfg
    return None


def _verdicts() -> list[dict]:
    """Every assertion verdict from the current runtimes, with its response attached."""
    out = []
    for g in sorted(RUNS.glob("*/*/*/grading.json")):
        scenario = g.parts[-4]
        cell = g.parts[-3]
        parsed = _split_cell(cell)
        if parsed is None:
            continue
        model, config = parsed
        if model not in CURRENT:
            continue
        resp = g.parent / "response.md"
        if not resp.exists():
            continue
        data = json.loads(g.read_text())
        for i, e in enumerate(data.get("expectations", [])):
            out.append({
                "id": f"{scenario}|{cell}|{g.parent.name}|{i}",
                "scenario": scenario, "model": model, "config": config,
                "run": g.parent.name, "index": i,
                "assertion": e.get("text", ""),
                "grader_passed": bool(e.get("passed")),
                "grader_evidence": e.get("evidence", ""),
                "assertions_sha": data.get("assertions_sha", ""),
                "response_path": str(resp.relative_to(REPO)),
            })
    return out


def cmd_sample(*, n: int, seed: int) -> int:
    items = _verdicts()
    if not items:
        print("✗ no verdicts found under results/runs for the current runtimes.\n"
              "  Either the path is wrong or CURRENT is stale. Not sampling nothing and "
              "calling it a sample.", file=sys.stderr)
        return 2

    # Stratify on BOTH the grader's verdict and the arm, four cells of equal size.
    #
    # Verdict, because failures are ~21% of the population and a uniform draw of 60 yields
    # ~13 of them: too few to say anything about the false-pass rate, which is the direction
    # that inflates every published score.
    #
    # Arm, because the question this exists to answer is whether the grader treats treatment
    # responses differently from baseline ones, and an unbalanced draw answers it with
    # unequal power per cell. Stratifying on verdict alone produced 34 baseline against 26
    # with_skill, which is not fatal but spends scarce human labelling effort unevenly across
    # the comparison it is funding.
    rng = random.Random(seed)
    strata = {}
    for v in items:
        strata.setdefault((v["config"], v["grader_passed"]), []).append(v)
    per = n // len(strata)
    thin = {k: len(v) for k, v in strata.items() if len(v) < per}
    if thin:
        print(f"✗ cannot draw {per} from every stratum; short in {thin}.\n"
              f"  Lower --sample, or accept an unbalanced draw deliberately rather than by "
              f"accident.", file=sys.stderr)
        return 2
    draw = []
    for k in sorted(strata):
        draw += rng.sample(strata[k], per)
    # any remainder from integer division goes to the largest strata, deterministically
    if len(draw) < n:
        rest = [v for v in items if v not in draw]
        draw += rng.sample(rest, n - len(draw))
    rng.shuffle(draw)                      # so the worksheet order leaks nothing

    # Coverage, asserted rather than assumed. The stratification check above only proves
    # enough items EXIST in each verdict stratum; it cannot notice that an entire arm is
    # absent from the population, which is exactly how the first sample came back 100%
    # baseline and looked like a clean draw. Balance is not coverage.
    pop_arms = {v["config"] for v in items}
    pop_models = {v["model"] for v in items}
    got_arms = {v["config"] for v in draw}
    got_models = {v["model"] for v in draw}
    gaps = []
    if len(pop_arms) < 2:
        gaps.append(f"the POPULATION holds only {sorted(pop_arms)}; a grader validated on one "
                    f"arm says nothing about the comparison between arms")
    if pop_arms - got_arms:
        gaps.append(f"arms present on disk but absent from the draw: {sorted(pop_arms - got_arms)}")
    if pop_models - got_models:
        gaps.append(f"models missing from the draw: {sorted(pop_models - got_models)}")
    if gaps:
        print("✗ sample does not cover what it claims to:", file=sys.stderr)
        for g_ in gaps:
            print(f"    {g_}", file=sys.stderr)
        print("\n  Raise --sample, or fix the filter. A balanced sample of the wrong "
              "population\n  is still the wrong population.", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample.jsonl").write_text(
        "".join(json.dumps(v) + "\n" for v in draw))

    # The blind worksheet. No grader verdict, no grader evidence.
    lines = [
        "# Grader validation worksheet",
        "",
        f"{len(draw)} assertion verdicts, drawn 50/50 on the grader's verdict (which is not "
        f"shown to you) with seed {seed}. Sample and seed are recorded in sample.jsonl.",
        "",
        "For each item: read the response, decide whether the assertion holds, and write "
        "`PASS` or `FAIL` on the verdict line. Write `UNCLEAR` if the assertion cannot be "
        "decided from the response; those are reported separately and are a finding about "
        "the assertion, not about you.",
        "",
        "Do not skip items. `--report` refuses to score a partial worksheet, because "
        "grading only the easy ones is how a validation comes back clean.",
        "",
        "---",
        "",
    ]
    for k, v in enumerate(draw, 1):
        response = (REPO / v["response_path"]).read_text(errors="ignore").strip()
        lines += [
            f"## {k}. `{v['id']}`",
            "",
            f"**Assertion:** {v['assertion']}",
            "",
            "**Verdict:** ",
            "",
            "<details><summary>response</summary>",
            "",
            "```",
            response,
            "```",
            "",
            "</details>",
            "",
            "---",
            "",
        ]
    (OUT / "worksheet.md").write_text("\n".join(lines))
    arm_counts = collections.Counter(v["config"] for v in draw)
    npass = sum(1 for v in draw if v["grader_passed"])
    print(f"✓ {len(draw)} items ({npass} the grader passed, {len(draw) - npass} it failed)")
    print(f"  arms: {dict(sorted(arm_counts.items()))}")
    print(f"  models: {len(got_models)} of {len(pop_models)}")
    print(f"  {OUT/'sample.jsonl'}")
    print(f"  {OUT/'worksheet.md'}   <- label this, then run --report")
    return 0


# Cross-VENDOR graders, not just a second Claude. Two models from one family share training
# and share blind spots, so their agreement mostly measures that shared lineage. Claude,
# OpenAI and Google disagreeing is weak evidence of ambiguity; the three agreeing is still
# not proof of correctness, but it is the strongest signal available without a human.
GRADERS = {
    "claude": lambda prompt, m: ["claude", "-p", prompt, "--model", m],
    "codex":  lambda prompt, m: ["codex", "exec", "--sandbox", "read-only", "--ephemeral",
                                 "-m", m, "-C", str(REPO), prompt],
    "agy":    lambda prompt, m: ["agy", "--mode", "plan", "--add-dir", str(REPO),
                                 "--model", m, "-p", prompt],
}
DEFAULT_MODEL = {"claude": "claude-opus-4-5", "codex": "gpt-5.6-terra",
                 "agy": "gemini-3.1-pro-high"}


def _extract_verdict(raw: str) -> dict:
    """Pull the JSON object out of a reply. Returns an error record rather than a verdict when
    it cannot, because a failed parse scored as False becomes a silent disagreement and moves
    the agreement figure without anything reporting a problem."""
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        obj = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"error": raw[:400] or "empty reply"}
    if "passed" not in obj:
        return {"error": f"no 'passed' key in {list(obj)[:6]}"}
    return {"passed": bool(obj["passed"]), "evidence": str(obj.get("evidence", ""))[:400]}


def cmd_focus(*, controls: int, seed: int) -> int:
    """Worksheet of every contested verdict plus a blind sample of unanimous ones.

    Labelling only the contested items would measure accuracy on the hard cases, which is a
    lower bound rather than an estimate, and would be structurally blind to the failure that
    matters most: all three graders agreeing and all three being wrong. Unanimity is evidence
    of consistency, not of correctness, and nothing in a contested-only worksheet could ever
    reveal that.

    So the unanimous controls are mixed in and shuffled. The labeller cannot tell which is
    which, because knowing an item was contested is exactly the hint that would make them
    scrutinise it harder and turn the comparison into a measurement of effort.
    """
    contested_f = OUT / "contested.json"
    if not contested_f.exists():
        print("✗ no contested.json; run --report after both second graders finish.",
              file=sys.stderr)
        return 2
    contested = json.loads(contested_f.read_text())
    items = {json.loads(l)["id"]: json.loads(l)
             for l in (OUT / "sample.jsonl").read_text().splitlines() if l.strip()}
    contested_ids = {c["id"] for c in contested}

    others = [i for i in items if i not in contested_ids]
    rng = random.Random(seed)
    picked = rng.sample(others, min(controls, len(others)))
    focus = [items[i] for i in sorted(contested_ids)] + [items[i] for i in picked]
    rng.shuffle(focus)

    (OUT / "focus.jsonl").write_text("".join(json.dumps(v) + "\n" for v in focus))
    lines = [
        "# Focused validation worksheet",
        "",
        f"{len(focus)} assertion verdicts: every item the three graders split on, plus "
        f"{len(picked)} they agreed on, shuffled together. **Which is which is not shown, and "
        f"should not be guessed at** — knowing an item was contested is the hint that would "
        f"turn this into a measurement of how hard you looked.",
        "",
        "Read the response, decide whether the assertion holds, write `PASS`, `FAIL` or "
        "`UNCLEAR` on the verdict line. `UNCLEAR` is a finding about the assertion, not about "
        "you: an assertion three frontier models split on is usually ambiguous.",
        "",
        "---",
        "",
    ]
    for k, v in enumerate(focus, 1):
        response = (REPO / v["response_path"]).read_text(errors="ignore").strip()
        lines += [
            f"## {k}. `{v['id']}`", "",
            f"**Assertion:** {v['assertion']}", "",
            "**Verdict:** ", "",
            "<details><summary>response</summary>", "", "```", response, "```", "",
            "</details>", "", "---", "",
        ]
    (OUT / "focus.md").write_text("\n".join(lines))
    print(f"✓ {len(focus)} items: {len(contested_ids)} contested + {len(picked)} unanimous")
    print(f"  {OUT/'focus.md'}   <- label this, then --report")
    return 0


def cmd_second_grader(model: str) -> int:
    sample = OUT / "sample.jsonl"
    if not sample.exists():
        print("✗ no sample.jsonl; run --sample first.", file=sys.stderr)
        return 2
    vendor, _, model_id = model.partition(":")
    if vendor not in GRADERS:
        print(f"✗ unknown grader '{vendor}'. Use one of: {', '.join(GRADERS)}, "
              f"optionally as vendor:model.", file=sys.stderr)
        return 2
    model_id = model_id or DEFAULT_MODEL[vendor]
    items = [json.loads(l) for l in sample.read_text().splitlines() if l.strip()]
    if LIMIT[0]:
        items = items[:LIMIT[0]]
    results = {}
    for k, v in enumerate(items, 1):
        response = (REPO / v["response_path"]).read_text(errors="ignore")
        prompt = SECOND_GRADER_PROMPT.format(assertion=v["assertion"], response=response)
        cmd = GRADERS[vendor](prompt, model_id)
        try:
            r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                               timeout=SECOND_GRADER_TIMEOUT_S)
            raw = (r.stdout or "").strip()
            results[v["id"]] = _extract_verdict(raw) if raw else {
                "error": (r.stderr or "no output")[:400]}
        except subprocess.TimeoutExpired:
            results[v["id"]] = {"error": f"timeout after {SECOND_GRADER_TIMEOUT_S}s"}
        print(f"  {k}/{len(items)}", end="\r", flush=True)
    (OUT / f"second-grader-{vendor}.json").write_text(json.dumps(results, indent=1))
    bad = sum(1 for v in results.values() if "error" in v)
    print(f"\n✓ {len(results)} regraded by {vendor} ({model_id}), {bad} unusable")
    return 0


def _kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's kappa. Raw agreement alone flatters any skewed population: a grader that
    answers PASS every time scores 79% against a population that is 79% passes."""
    n = len(a)
    obs = sum(1 for x, y in zip(a, b) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    exp = pa * pb + (1 - pa) * (1 - pb)
    return (obs - exp) / (1 - exp) if exp < 1 else 1.0


def cmd_report() -> int:
    sample = OUT / "sample.jsonl"
    if not sample.exists():
        print("✗ no sample.jsonl; run --sample first.", file=sys.stderr)
        return 2
    items = {json.loads(l)["id"]: json.loads(l)
             for l in sample.read_text().splitlines() if l.strip()}

    labels, unclear = {}, []
    # Prefer the focused worksheet when one exists: it is the one a human was asked to fill.
    focus = OUT / "focus.jsonl"
    if focus.exists():
        items = {json.loads(l)["id"]: json.loads(l)
                 for l in focus.read_text().splitlines() if l.strip()}
    ws = OUT / "focus.md" if (OUT / "focus.md").exists() else OUT / "worksheet.md"
    if ws.exists():
        cur = None
        for line in ws.read_text().splitlines():
            if line.startswith("## ") and "`" in line:
                cur = line.split("`")[1]
            elif line.startswith("**Verdict:**") and cur:
                v = line.split("**Verdict:**", 1)[1].strip().upper()
                if v in ("PASS", "FAIL"):
                    labels[cur] = (v == "PASS")
                elif v == "UNCLEAR":
                    unclear.append(cur)
                cur = None

    print(f"sample            : {len(items)} verdicts")
    print(f"human-labelled    : {len(labels)}   unclear: {len(unclear)}")

    missing = len(items) - len(labels) - len(unclear)
    if missing:
        # Scoring the labelled subset would report an agreement figure computed from
        # whichever items happened to be easy enough to label. That is the shape of every
        # bug this repo exists to catch, so it is refused rather than warned about.
        print(f"\n✗ {missing} items unlabelled. Refusing to report agreement on a partial "
              f"worksheet:\n  the labelled subset is not a random subset, it is the subset "
              f"someone found easy.", file=sys.stderr)
        return 1

    if labels:
        ids = sorted(labels)
        human = [labels[i] for i in ids]
        grader = [items[i]["grader_passed"] for i in ids]
        agree = sum(1 for a, b in zip(human, grader) if a == b)
        fp = sum(1 for i in ids if items[i]["grader_passed"] and not labels[i])
        fn = sum(1 for i in ids if not items[i]["grader_passed"] and labels[i])
        print(f"\n--- grader vs human (ACCURACY) ---")
        print(f"  raw agreement   : {agree}/{len(ids)}  ({agree*100//len(ids)}%)")
        print(f"  Cohen's kappa   : {_kappa(human, grader):.3f}")
        print(f"  grader passed, human failed (false pass): {fp}   <- inflates every score")
        print(f"  grader failed, human passed (false fail): {fn}")
        if unclear:
            print(f"  undecidable assertions  : {len(unclear)}  <- fix the assertion text")

    for f in sorted(OUT.glob("second-grader-*.json")):
        model = f.stem.replace("second-grader-", "")
        second = json.loads(f.read_text())
        ids = [i for i in items if i in second and "error" not in second[i]]
        if not ids:
            continue
        a = [items[i]["grader_passed"] for i in ids]
        b = [bool(second[i].get("passed")) for i in ids]
        agree = sum(1 for x, y in zip(a, b) if x == y)
        print(f"\n--- grader vs {model} (RELIABILITY, not accuracy) ---")
        print(f"  raw agreement   : {agree}/{len(ids)}  ({agree*100//len(ids)}%)")
        print(f"  Cohen's kappa   : {_kappa(a, b):.3f}")
        print(f"  two models agreeing is not evidence they are right; a shared blind spot")
        print(f"  agrees perfectly. Only the human column above speaks to accuracy.")

    if not labels:
        print("\n(no human labels yet: worksheet.md is unlabelled, so accuracy is unmeasured)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", type=int, metavar="N", help="draw N verdicts, 50/50 on verdict")
    g.add_argument("--second-grader", metavar="VENDOR[:MODEL]",
                   help="re-grade the sample blind: claude, codex or agy")
    g.add_argument("--report", action="store_true", help="agreement figures")
    g.add_argument("--focus", type=int, nargs="?", const=8, metavar="N",
                   help="worksheet of every contested item plus N unanimous controls")
    p.add_argument("--limit", type=int, default=0,
                   help="only regrade the first N items, for proving the plumbing")
    p.add_argument("--seed", type=int, default=20260824, help="sampling seed (recorded)")
    a = p.parse_args()
    if a.sample:
        return cmd_sample(n=a.sample, seed=a.seed)
    if a.focus is not None:
        return cmd_focus(controls=a.focus, seed=a.seed)
    if a.second_grader:
        LIMIT[0] = a.limit
        return cmd_second_grader(a.second_grader)
    return cmd_report()


if __name__ == "__main__":
    sys.exit(main())
