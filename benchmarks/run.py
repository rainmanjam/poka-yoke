#!/usr/bin/env python3
"""Poka-yoke benchmark harness, baseline vs with-skill, across models.

Runs every scenario in scenarios.json under two configurations (no skill / with the
plugin's router skill), N times each, on one or more models. Grades blind against
pre-written assertions, then aggregates.

Design notes, since they are the difference between a benchmark and a number:

  * Runs get --allowedTools Read,Grep,Glob. The benchmark cannot write to the repo
    because the tool list makes writing unrepresentable, rather than because a prompt
    asked it not to.
  * Grading is BLIND and BATCHED. The grader sees responses labelled A/B/C with the
    checklist, never which model or configuration produced them. Batching one call per
    cell cuts grading calls by the number of runs per cell.
  * Every scenario is a prompt in which the user has already applied a fix that is
    insufficient, so agreeing with them scores badly. This measures pushback, not recall.
  * Resumable: a run with an existing response.md is skipped and a graded run is not
    re-graded, so an interrupted sweep continues rather than restarting.

Rate-limit safety: an earlier version of this harness ran 720 calls at 16 workers and
exhausted a session limit, then recorded 172 rate-limit replies as JSON parse errors.
Four devices now prevent that:

  * --max-calls is a HARD ceiling. The harness raises and stops rather than exceeding it.
    Overrunning is impossible, not merely discouraged.
  * Rate-limit replies are detected and retried with exponential backoff, instead of
    being mistaken for malformed output.
  * Default concurrency is 4 with pacing between calls.
  * Grading is batched and defaults to a small model, because checklist scoring is
    classification, not reasoning.

Usage:
    python3 benchmarks/run.py                              # full sweep
    python3 benchmarks/run.py --grade-only                 # grade existing runs
    python3 benchmarks/run.py --runs 1 --scenarios ux      # quick smoke test
    python3 benchmarks/run.py --aggregate-only             # re-aggregate
    python3 benchmarks/run.py --dry-run                    # show the call budget, do nothing
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import statistics as st
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS = HERE / "results"
SKILL_ROUTER = REPO / "plugins/poka-yoke/skills/poka-yoke/SKILL.md"
PLUGIN_ROOT = REPO / "plugins/poka-yoke"

# Control arms. `baseline` vs `with_skill` alone cannot separate "this method works" from
# "any structured methodology in context works", so every published delta was equally
# consistent with both readings. Each ARM below is a router the model is told to read and
# follow, exactly as with_skill is, so the mechanism is matched and only the content differs.
#
#   with_placebo    real but unrelated quality guidance (naming, cohesion, coupling).
#                   Isolates the method from the mere presence of a methodology document.
#   with_defensive  the methodology this project argues against. Turns the central
#                   rhetorical claim of the video and the README into a measured one.
#
# These are NOT shipped with the plugin; they exist only to be beaten, or not.
ARMS = {
    "with_skill":     (SKILL_ROUTER, PLUGIN_ROOT),
    "with_placebo":   (REPO / "benchmarks/controls/clean-code/skills/clean-code/SKILL.md",
                       REPO / "benchmarks/controls/clean-code"),
    "with_defensive": (REPO / "benchmarks/controls/defensive/skills/defensive/SKILL.md",
                       REPO / "benchmarks/controls/defensive"),
}

CONFIGS = ["baseline", "with_skill", "with_placebo", "with_defensive"]

# The standing matrix. Opus 4.5 and Sonnet 4.5 runs also exist under results/ from an
# earlier sweep; they are kept as data but are not part of the reported benchmark.
# (Sonnet 4 retired 2025-06-15 and Haiku 3.5 retired 2026-02-19, so Haiku has only one
# live version and no version comparison is possible.)
# Ordered strongest-to-weakest on this benchmark, so tables read Fable -> Haiku.
MODELS = {
    "fable":                      "Fable 5",
    "opus":                       "Opus 5",
    "claude-sonnet-5":            "Sonnet 5",
    "claude-haiku-4-5-20251001":  "Haiku 4.5",
}
EXTRA_MODELS = {"claude-opus-4-5": "Opus 4.5", "claude-sonnet-4-5-20250929": "Sonnet 4.5"}

# Runners for non-Claude CLIs. `cmd` is built per call; {prompt} is substituted, never
# shell-interpolated. `readonly` records whether the runner can be made structurally unable
# to write: the benchmark's central design claim, because it is NOT true of every CLI and
# a footnote is not a device.
#
#   claude  --allowedTools Read,Grep,Glob   the tool list makes writing unrepresentable
#   codex   --sandbox read-only             the sandbox refuses writes
#   agy     --mode plan --add-dir <repo>    plan mode refuses writes; --add-dir grants the
#                                           reads the with-skill arm needs. Verified rather
#                                           than assumed: asked to overwrite a canary and
#                                           create a file, plan mode did neither, while
#                                           --dangerously-skip-permissions did both. Bare
#                                           --sandbox is NOT the answer. It denies reads
#                                           too, so the with-skill arm cannot open SKILL.md
#                                           and every run returns empty.
SCHEMA_INLINE = HERE / "schemas" / "inline-answer.json"

# Scenario/model pairs that cannot be run, with the reason. Recorded here rather than left
# as a hole in the data, because an absent cell is indistinguishable from a lost one, and a
# column quietly averaging a smaller suite than its neighbours is the exact defect that made
# Sonnet 5 read +8.8 pp against a delta its own two numbers did not produce.
NOT_RUNNABLE = {
    ("audit", "agy-gemini-3.1-pro"):
        "the audit skill runs the bundled detector, and agy in print mode refuses to execute "
        "a command in EVERY permission mode it offers. Tested: --mode plan and --mode "
        "accept-edits both fail with 'permission check failed', and --sandbox denies reads "
        "as well. Only --dangerously-skip-permissions executes, and it grants writes too, "
        "verified against a canary file, which it overwrote. There is no exec-without-write "
        "setting, so the read-only guarantee the other five columns carry cannot be kept "
        "while running this skill.",
}


def _agy_extract(out: str) -> str:
    """Recover agy's actual answer, which is usually not in its chat reply.

    agy writes its work to a markdown artifact under its own brain directory and returns a
    cover note with a file:// link, 58% of scenarios in the first sweep. Those runs scored
    0 because the reply genuinely contained no design, which measured delivery format rather
    than quality. `--json-schema` does not fix it: structured_output.answer is populated but
    holds a 40-85 word summary, not the work.

    So follow the pointer. The artifact IS the deliverable; the reply is a covering note.
    This is a runtime-specific accommodation and it is worth naming: agy is then graded on a
    written plan while the other runtimes are graded on a chat answer. Without it agy is
    graded on a hyperlink, which is worse.
    """
    try:
        j = json.loads(out)
        reply = (j.get("response") or "").strip()
        so = j.get("structured_output")
        summary = so["answer"].strip() if isinstance(so, dict) and isinstance(so.get("answer"), str) else ""
    except json.JSONDecodeError:
        reply, summary = out.strip(), ""

    # agy sometimes nests another JSON object inside the answer string, e.g.
    # {"answer":"...","toolAction":"Finishing interaction"}. Stored raw, that is an error
    # wearing a response's clothes: the preflight caught one and was right to.
    def unwrap(t: str) -> str:
        t = t.strip()
        if t.startswith("{") and '"answer"' in t:
            try:
                inner = json.loads(t)
                if isinstance(inner.get("answer"), str):
                    return inner["answer"].strip()
            except json.JSONDecodeError:
                pass
        return t

    reply, summary = unwrap(reply), unwrap(summary)
    best = max((reply, summary), key=lambda t: len(t.split()))

    # Follow the conversation, not just the link. agy sometimes says "review the plan in the
    # artifacts" and gives no file:// URL at all, 11 of 75 runs in the first full sweep. The
    # reply is then a covering note for work the grader never sees, and the cell scores as if
    # the model said nothing. Artifacts live at brain/<conversation_id>/<name>.md, and the
    # envelope carries the id, so the plan is findable whether or not it was linked.
    # poka-yoke: recovers the answer from the conversation directory, so work delivered as an unlinked artifact cannot be graded as silence [detection]
    cid = ""
    try:
        cid = str(json.loads(out).get("conversation_id") or "")
    except (json.JSONDecodeError, TypeError):
        pass
    if cid:
        brain = Path.home() / ".gemini" / "antigravity-cli" / "brain" / cid
        if brain.is_dir():
            for art in brain.glob("*.md"):
                try:
                    t = art.read_text().strip()
                except OSError:
                    continue
                if len(t.split()) > len(best.split()):
                    best = t
    for m in re.finditer(r"file://(/[^\s)\]]+\.md)", reply + "\n" + summary):
        try:
            art = Path(m.group(1)).read_text().strip()
        except OSError:
            continue
        if len(art.split()) > len(best.split()):
            best = art
    return best


RUNNERS = {
    "codex-gpt-5.6-terra": {
        "label": "Codex",
        # -m is pinned rather than inherited: without it the column said "Codex" and ran
        # whatever ~/.codex/config.toml happened to hold. --ephemeral keeps a sweep from
        # leaving session state that a later run could pick up.
        "cmd": lambda prompt, model: [
            "codex", "exec", "--sandbox", "read-only", "--ephemeral",
            "-m", "gpt-5.6-terra", "-C", str(REPO), prompt],
        "readonly": True,
        # Measured 9-28s per run against Claude's 60-190s, and no throttling across a
        # 16-run smoke sweep. The Claude pacing exists because a session limit was actually
        # exhausted; applying it here would trade an hour of wall-clock for nothing.
        "pace": 0.6, "workers": 4,
    },
    "agy-gemini-3.1-pro": {
        "label": "agy",
        "extract": _agy_extract,
        "cmd": lambda prompt, model: [
            "agy", "--mode", "plan", "--add-dir", str(REPO),
            "--model", "gemini-3.1-pro-high",
            "--output-format", "json", "--json-schema", str(SCHEMA_INLINE),
            "-p", prompt],
        "readonly": True,
        "pace": 0.3, "workers": 4,
    },
}

label = lambda m: (MODELS.get(m) or EXTRA_MODELS.get(m)
                   or (RUNNERS[m]["label"] if m in RUNNERS else m))


def is_readonly(model: str) -> bool:
    """Whether this model's runs were structurally prevented from writing."""
    return RUNNERS[model]["readonly"] if model in RUNNERS else True

# A run that died because the read-only constraint blocked a tool the model chose to reach
# for. Claude's runs cannot hit this: an allowlisted tool set means the tool is simply absent
# and the model adapts inside the same run. agy aborts the whole turn instead, so ~20% of its
# runs returned nothing: a harness artefact, not a quality signal. Retried like a throttle,
# and counted, because selecting only for turns that never reached for a shell is a bias worth
# stating rather than hiding.
BLOCKED_TOOL_RE = re.compile(r"permission check failed|user denied permission", re.I)
BLOCKED_RETRIES = {"n": 0}


# poka-yoke: reads the blocked-tool error from the JSON envelope as well as stderr, so a refused tool cannot be recorded as an empty answer [detection]
def _blocked(out: str, err: str) -> bool:
    """Did this turn die because the read-only constraint refused a tool?

    agy reports it two different ways depending on --output-format: on stderr in text mode,
    and inside a JSON envelope as {"status": "ERROR", "error": "..."} in json mode. The first
    version only read stderr, so once the runner moved to json output every one of these
    became a silent `(empty)` and the retry never fired, `audit` lost all three with-skill
    runs that way, because the skill tells the model to run the detector and plan mode
    refuses to execute python.

    Matched against the error field specifically, never the whole body: a long answer that
    happens to discuss permissions is not a blocked tool, and that is the same mistake the
    rate-limit pattern already made once.
    """
    if BLOCKED_TOOL_RE.search(err):
        return True
    try:
        j = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return False
    return (j.get("status") == "ERROR"
            and bool(BLOCKED_TOOL_RE.search(str(j.get("error", "")))))

RATE_LIMIT_RE = re.compile(
    r"rate.?limit|too many requests|429|usage limit|quota|overloaded|"
    r"session limit|try again later|capacity", re.I)


class BudgetExceeded(RuntimeError):
    """The hard call ceiling was reached. Raised rather than silently continuing."""


class Budget:
    """A hard ceiling on CLI invocations. This is the device that makes the failure
    that produced this class impossible rather than unlikely."""

    def __init__(self, limit: int):
        self.limit, self.used, self._lock = limit, 0, threading.Lock()

    # poka-yoke: refuses to exceed the call ceiling, so a sweep cannot exhaust a session limit [control]
    def take(self) -> int:
        with self._lock:
            if self.used >= self.limit:
                raise BudgetExceeded(
                    f"call budget of {self.limit} reached; stopping. "
                    f"Re-run to continue (completed work is skipped), or raise --max-calls.")
            self.used += 1
            return self.used

    def remaining(self) -> int:
        with self._lock:
            return self.limit - self.used


BUDGET: Budget | None = None
PACE = 0.0

def preamble_for(config: str) -> str:
    """The same instruction for every arm, with only the paths swapped.

    Wording is shared deliberately. If the treatment preamble said "follow this rigorously"
    and a control said "consider this", the comparison would measure the preamble rather than
    the methodology, and nothing downstream would reveal it.
    """
    router, root = ARMS[config]
    return (
        f"Before answering, read {router}. It is a router skill. Follow its routing to the\n"
        f"matching sub-skill under {root}/skills/, read that sub-skill in full, and read any\n"
        f"reference files it points to. Paths written as ${{CLAUDE_PLUGIN_ROOT}}/ resolve to\n"
        f"{root}/. Follow the skill's instructions faithfully, then answer the user.\n"
        "\nThe user's message:\n\n"
    )



GRADER_PROMPT = """\
You are grading {n} independent responses to the same user message against one checklist.
You do not know how any of them were produced, and that is deliberate, judge only what is
on the page, and judge each response entirely on its own.

THE USER'S ORIGINAL MESSAGE:
{prompt}

CHECKLIST, for each response, decide for each item whether that response does the thing:
{assertions}

{responses}

Rules:
- Strict and literal. An item passes only if the response genuinely does it. Gesturing at a
  topic is not doing it.
- Do not reward length, effort, confidence, structure, or vocabulary. A short response that
  does the thing passes; a long one that circles it does not.
- Judge each response independently. Do not compare them or let one influence another.
- Judge only against the checklist. Do not add criteria of your own.

Output ONLY a JSON object mapping each response letter to its results, no prose:
{{{{"A": {{{{"expectations": [{{{{"text": "<item verbatim>", "passed": true, "evidence": "<short real quote, or what was absent>"}}}}]}}}}}}}}
"""


def run_cli(prompt: str, model: str, tools: str | None,
            timeout: int = 900, retries: int = 4) -> tuple[str, float, str]:
    """Invoke a model CLI headless, with backoff on rate limits.

    Returns (stdout, elapsed_seconds, error). error is "" on success, otherwise a short
    reason, crucially distinguishing a rate limit from malformed output, which the
    previous version conflated and recorded as 172 bogus JSON errors.

    Non-Claude models are dispatched through RUNNERS; everything else, blind batched
    grading, the call ceiling, rate-limit backoff, provenance, is identical, so a Codex
    or agy column is comparable to a Claude one except where `is_readonly` says otherwise.
    """
    t0 = time.time()
    for attempt in range(retries):
        if BUDGET:
            BUDGET.take()
        pace = RUNNERS.get(model, {}).get("pace", PACE)
        if pace:
            time.sleep(pace)
        if model in RUNNERS:
            cmd = RUNNERS[model]["cmd"](prompt, model)
        else:
            cmd = ["claude", "-p", prompt, "--model", model]
            if tools:
                cmd += ["--allowedTools", tools]
        try:
            r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                               timeout=timeout, env={**os.environ, "SSH_AUTH_SOCK": ""})
        except subprocess.TimeoutExpired:
            return "", time.time() - t0, "timeout"

        out, err = (r.stdout or "").strip(), (r.stderr or "").strip()
        # A rate-limit NOTICE is short and usually on stderr. A long answer that happens to
        # discuss rate limiting is not one, but the first version matched the pattern
        # anywhere in stdout+stderr, so an `audit` response recommending a rate limit was
        # discarded, retried four times, and finally recorded as "rate limited after
        # retries". One stored response in 514 trips it, which is exactly rare enough to
        # never be noticed and always be wrong.
        # A rate limit means you did not get an answer. If stdout holds a substantial
        # response, the run succeeded no matter what either stream says about rate limiting.
        #
        # Narrowing stdout alone was not enough. Codex echoes the whole prompt to stderr, and
        # the `llm` scenario is ABOUT llm guardrails. Its skill text lists "refusal, timeout,
        # rate limit, empty retrieval" as failure modes to handle. So every `llm` with-skill
        # run matched, was discarded, retried four times and recorded as "rate limited after
        # retries". Six sweeps and roughly 24 calls went on a cell that answered correctly
        # every single time, and the column shipped a documented gap that did not exist.
        answered = len(out.split()) >= 120
        limited = (not answered) and (
            bool(RATE_LIMIT_RE.search(err)) or bool(RATE_LIMIT_RE.search(out)))
        if out and _blocked(out, err):
            BLOCKED_RETRIES["n"] += 1
            print(f"      tool blocked by the read-only constraint, retrying "
                  f"(attempt {attempt+1}/{retries})", flush=True)
            time.sleep(2)
            continue
        if out and not limited:
            ex = RUNNERS.get(model, {}).get("extract")
            if ex:
                out = ex(out)
            return out, time.time() - t0, ""
        if not limited:
            if _blocked(out, err):
                BLOCKED_RETRIES["n"] += 1
                print(f"      tool blocked by the read-only constraint, retrying "
                      f"(attempt {attempt+1}/{retries})", flush=True)
                time.sleep(2)
                continue
            return out, time.time() - t0, ("empty output" if not out else "")

        wait = min(60, 4 * 2 ** attempt) + random.uniform(0, 3)
        print(f"      rate limited, backing off {wait:.0f}s "
              f"(attempt {attempt+1}/{retries})", flush=True)
        time.sleep(wait)
    return "", time.time() - t0, "rate limited after retries"


def prompt_sha(sc: dict) -> str:
    """Identity of the question a run answered, so an edited scenario invalidates its runs."""
    return hashlib.sha256(sc["prompt"].encode()).hexdigest()[:12]


def assertions_sha(sc: dict) -> str:
    """Identity of the checklist a grading was produced against.

    `prompt_sha` makes an edited *question* invalidate its runs. Nothing did the same for an
    edited *answer key*: `grade_cell` skipped any run that already had a grading.json, so
    rewriting an assertion left every stored grading scored against a checklist that no
    longer existed, and the harness would go on reporting those numbers without a word.
    Same failure, other half of the pair.
    """
    return hashlib.sha256("\n".join(sc["assertions"]).encode()).hexdigest()[:12]


def run_dir(scenario: str, model: str, config: str, n: int) -> Path:
    return RESULTS / "runs" / scenario / f"{model}_{config}" / f"run-{n}"


def cell_runs(scenario: str, model: str, config: str) -> list[int]:
    """Run numbers present on disk for a cell, ascending.

    Aggregation asks the filesystem what was actually measured rather than trusting a
    flag to describe it. `--runs` says how many to *produce*; it has no business
    deciding how many to *count*.
    """
    cell = RESULTS / "runs" / scenario / f"{model}_{config}"
    if not cell.is_dir():
        return []
    ns = []
    for d in cell.iterdir():
        if d.is_dir() and d.name.startswith("run-") and d.name[4:].isdigit():
            ns.append(int(d.name[4:]))
    return sorted(ns)


def do_run(sc: dict, model: str, config: str, n: int) -> str:
    d = run_dir(sc["id"], model, config, n)
    resp, meta = d / "response.md", d / "timing.json"
    # A run is only reusable if it answered the CURRENT prompt. Editing a scenario used to
    # leave old runs in place, silently mixing two different questions into one result , 
    # the resume logic had no way to know. Stamping the prompt hash makes that impossible.
    if resp.exists() and resp.stat().st_size > 200:
        stale = True
        if meta.exists():
            try:
                stale = json.loads(meta.read_text()).get("prompt_sha") != prompt_sha(sc)
            except (json.JSONDecodeError, OSError):
                stale = True
        if not stale:
            return f"skip run   {sc['id']:18} {label(model):10} {config:11} run-{n}"
        for f in (resp, meta, d / "grading.json"):
            f.unlink(missing_ok=True)
        print(f"      prompt changed, discarding stale {sc['id']}/{model}/{config}/run-{n}",
              flush=True)
    d.mkdir(parents=True, exist_ok=True)

    prompt = (preamble_for(config) + sc["prompt"]) if config in ARMS else sc["prompt"]
    out, secs, err = run_cli(prompt, model, "Read,Grep,Glob")
    if err or not out:
        return f"FAIL run   {sc['id']:18} {label(model):10} {config:11} run-{n} ({err or 'empty'})"

    # Second device, at the write. An earlier version saved "You've hit your session
    # limit" into 164 response.md files, where it looked like a successful run and was
    # graded 0/8, 46% of a sweep silently turned into noise. Detection in claude()
    # should catch this; refusing the write means a poisoned response cannot be stored
    # even if detection misses. Cheap, and the failure it prevents was expensive.
    # poka-yoke: refuses to store a rate-limit message as if it were a response [control]
    if len(out) < 600 and RATE_LIMIT_RE.search(out):
        return f"FAIL run   {sc['id']:18} {label(model):10} {config:11} run-{n} (limit message, not saved)"

    resp.write_text(out)
    (d / "timing.json").write_text(json.dumps(
        {"seconds": round(secs, 1), "words": len(out.split()), "chars": len(out),
         "prompt_sha": prompt_sha(sc)}, indent=2))
    return f"ok   run   {sc['id']:18} {label(model):10} {config:11} run-{n}  {secs:5.0f}s {len(out.split()):5}w"


def grade_cell(sc: dict, model: str, config: str, runs: int, grader: str) -> str:
    """Grade every ungraded run in one cell with a single blind, batched call."""
    todo = []
    want = assertions_sha(sc)
    for n in cell_runs(sc["id"], model, config):
        d = run_dir(sc["id"], model, config, n)
        if not (d / "response.md").exists():
            continue
        g = d / "grading.json"
        if not g.exists():
            todo.append((n, d))
            continue
        try:
            have = json.loads(g.read_text()).get("assertions_sha")
        except json.JSONDecodeError:
            have = None
        # poka-yoke: regrades when the checklist changed, so a score cannot be reported against a superseded answer key [control]
        if have != want:
            # The checklist moved under a stored grading, so this run needs regrading.
            #
            # Do NOT delete the old grading first. An earlier version did, and when the
            # grader call then failed the data was simply gone: 11 gradings vanished that
            # way, and because a missing grading just shrinks a cell's n, the aggregate
            # dropped `authz` for Sonnet 5 entirely rather than reporting an error. The
            # write below overwrites on success, which is all that was ever needed , 
            # deleting up front bought nothing and cost the fallback.
            print(f"      assertions changed, regrading {sc['id']}/{model}/{config}/run-{n}",
                  flush=True)
            todo.append((n, d))
    if not todo:
        return f"skip grade {sc['id']:18} {label(model):10} {config:11} (nothing to grade)"

    letters = [chr(ord("A") + i) for i in range(len(todo))]
    blocks = "\n\n".join(
        f"RESPONSE {L}:\n---\n{d.joinpath('response.md').read_text()[:45000]}\n---"
        for L, (_, d) in zip(letters, todo))
    checklist = "\n".join(f"{i+1}. {a}" for i, a in enumerate(sc["assertions"]))

    out, _, err = run_cli(GRADER_PROMPT.format(
        n=len(todo), prompt=sc["prompt"], assertions=checklist, responses=blocks),
        grader, None)
    if err:
        return f"FAIL grade {sc['id']:18} {label(model):10} {config:11} ({err})"

    txt = out.strip()
    if "```" in txt:
        txt = txt.split("```")[1].removeprefix("json").strip()
    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            return f"FAIL grade {sc['id']:18} {label(model):10} {config:11} (unparseable)"
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return f"FAIL grade {sc['id']:18} {label(model):10} {config:11} (unparseable)"

    wrote = []
    for L, (n, d) in zip(letters, todo):
        exps = (data.get(L) or {}).get("expectations")
        if not isinstance(exps, list) or not exps:
            continue
        p = sum(1 for x in exps if x.get("passed"))
        (d / "grading.json").write_text(json.dumps(
            {"assertions_sha": want,
             "expectations": exps,
             "summary": {"passed": p, "total": len(exps),
                         "pass_rate": round(p / len(exps), 4)}}, indent=2))
        wrote.append(f"{p}/{len(exps)}")
    if not wrote:
        return f"FAIL grade {sc['id']:18} {label(model):10} {config:11} (no usable results)"
    return f"ok   grade {sc['id']:18} {label(model):10} {config:11}  {' '.join(wrote)}"


def preflight(purge: bool = False) -> int:
    """Find stored data that is not what it claims to be, before spending anything on it.

    This exists because a sweep once stored 164 rate-limit messages as responses and
    graded them 0/8, quietly turning 46% of the data into noise. Detecting that after the
    fact was luck. Making the check part of the tool means it cannot be forgotten.
    """
    root = RESULTS / "runs"
    if not root.exists():
        print("no results yet"); return 0

    suspect: list[tuple[Path, str]] = []
    for resp in root.rglob("response.md"):
        t = resp.read_text()
        if len(t) < 600 and RATE_LIMIT_RE.search(t):
            suspect.append((resp.parent, "limit/error message stored as a response"))
        elif len(t.strip()) < 250:
            suspect.append((resp.parent, f"implausibly short ({len(t.strip())} chars)"))
    for g in root.rglob("grading.json"):
        if not (g.parent / "response.md").exists():
            suspect.append((g.parent, "grading with no response"))
        elif json.loads(g.read_text())["summary"]["passed"] == 0:
            # A zero is only suspicious if the response cannot support one. This benchmark
            # is built so that agreeing with the user's insufficient fix scores badly, so a
            # long, well-formed answer CAN legitimately score 0, and one does: haiku told a
            # user whose CLAUDE.md was already in caps to use better markers in CLAUDE.md,
            # which is the rung-zero answer the assertions exist to catch.
            #
            # Flagging that as suspect invites --purge-suspect to delete it, which would
            # raise haiku's score by removing its worst legitimate result. A data check that
            # silently improves the numbers is worse than no check.
            body = (g.parent / "response.md")
            words = len(body.read_text().split()) if body.exists() else 0
            if words < 120:
                suspect.append((g.parent,
                                f"scored 0 and the response is only {words} words, "
                                "likely an error stored as a response"))

    total = len(list(root.rglob("response.md")))
    if not suspect:
        print(f"preflight: {total} stored runs, none suspect."); return 0

    print(f"preflight: {len(suspect)} suspect of {total} stored runs\n")
    seen = set()
    for d, why in suspect:
        if d in seen:
            continue
        seen.add(d)
        print(f"  {why:48} {d.relative_to(root)}")
    if purge:
        import shutil
        for d in seen:
            shutil.rmtree(d, ignore_errors=True)
        print(f"\npurged {len(seen)} directories; re-run to regenerate them")
    else:
        print(f"\n{len(seen)} directories. Re-run with --purge-suspect to delete and regenerate.")
    return len(seen)


def aggregate(scenarios: list[dict], models: list[str], runs: int) -> dict:
    # Provenance travels with the numbers. A reader cannot tell from a pass rate whether the
    # run behind it answered the prompt that is in the repository today, and the committed
    # data predates prompt-sha tracking entirely, so for those runs the honest answer is
    # "unverified". Recording it in the artifact means nobody has to remember the caveat.
    res: dict = {"scenarios": {}, "by_model": {},
                 "provenance": {"runs": 0, "prompt_verified": 0,
                                "no_prompt_sha": 0, "prompt_changed": 0}}
    for sc in scenarios:
        res["scenarios"][sc["id"]] = {}
        for model in models:
            if (sc["id"], model) in NOT_RUNNABLE:
                continue
            for config in CONFIGS:
                rates, secs, words = [], [], []
                # Read every run that exists, not `--runs` of them. Aggregating
                # range(1, runs+1) meant `--aggregate-only` with the default --runs 3
                # silently averaged run-1..run-3 and ignored run-4..run-7 that a later
                # sweep had already paid for: 264 of 486 runs counted, no warning, and a
                # published table that looked entirely healthy. The disk is the record.
                # poka-yoke: aggregates every run on disk, so a summary cannot be built from a subset of what was measured [control]
                for n in cell_runs(sc["id"], model, config):
                    d = run_dir(sc["id"], model, config, n)
                    if (d / "grading.json").exists():
                        rates.append(json.loads((d / "grading.json").read_text())["summary"]["pass_rate"])
                    if (d / "timing.json").exists():
                        ti = json.loads((d / "timing.json").read_text())
                        secs.append(ti["seconds"]); words.append(ti["words"])
                        pv = res["provenance"]
                        pv["runs"] += 1
                        sha = ti.get("prompt_sha")
                        if sha is None:
                            pv["no_prompt_sha"] += 1
                        elif sha == prompt_sha(sc):
                            pv["prompt_verified"] += 1
                        else:
                            pv["prompt_changed"] += 1
                if rates:
                    res["scenarios"][sc["id"]][f"{model}_{config}"] = {
                        "n": len(rates),
                        "pass_rate": round(st.mean(rates), 4),
                        "stdev": round(st.stdev(rates), 4) if len(rates) > 1 else 0.0,
                        "seconds": round(st.mean(secs), 1) if secs else None,
                        "words": round(st.mean(words)) if words else None,
                    }
    for model in models:
        res["by_model"][model] = {"label": label(model)}
        # Average both configurations over the SAME scenarios. Sonnet 5 once had
        # `build-agent-feature` with_skill but no baseline, six runs had failed and left
        # empty directories, so the baseline column averaged 12 scenarios, the with-skill
        # column 13, and the delta subtracted two different suites. The published row did
        # not even add up (88.5 - 78.7 = 9.8, printed as +8.8) and nothing objected.
        # poka-yoke: averages both configurations over the same scenarios, so a delta cannot subtract two different suites [control]
        # Pair over the arms that actually produced runs, not over every arm the harness
        # knows about. CONFIGS grew from two to four when the control arms were written, and
        # since neither control has ever been run, `all(... for c in CONFIGS)` made `paired`
        # empty for every model. Nothing noticed, because nobody re-aggregated between the
        # expansion and this review — the committed artifact was built when CONFIGS was two.
        # The first re-aggregation silently emptied every model row.
        # poka-yoke: pairs on the arms that have runs, so adding an unrun arm cannot empty every row [control]
        present = [c for c in CONFIGS
                   if any(f"{model}_{c}" in cells for cells in res["scenarios"].values())]
        if not present:
            continue
        paired = sorted(s for s, cells in res["scenarios"].items()
                        if all(f"{model}_{c}" in cells for c in present))
        res["by_model"][model]["arms_present"] = present
        blocked = sorted(s for (s, m) in NOT_RUNNABLE if m == model)
        if blocked:
            res["by_model"][model]["not_runnable"] = blocked
        res["by_model"][model]["paired_scenarios"] = len(paired)
        for config in present:
            key = f"{model}_{config}"
            vals = [res["scenarios"][s][key] for s in paired]
            if vals:
                pr = [v["pass_rate"] for v in vals]
                # `scenarios` counts cells; `runs` counts the runs behind them. Without the
                # second number a row built from thirteen single-run cells is indistinguishable
                # from one built from thirteen seven-run cells, and this is the table people
                # actually read. Carrying the resolution beside the number is cheaper than
                # expecting a reader to go and find it.
                # poka-yoke: publishes how many runs a model row rests on, so a thin cell cannot read like a thick one [detection]
                cell_ns = [v["n"] for v in vals]
                res["by_model"][model][config] = {
                    "pass_rate": round(st.mean(pr), 4),
                    "stdev": round(st.stdev(pr), 4) if len(pr) > 1 else 0.0,
                    "seconds": round(st.mean([v["seconds"] for v in vals if v["seconds"]]), 1),
                    "words": round(st.mean([v["words"] for v in vals if v["words"]])),
                    "scenarios": len(vals),
                    "runs": sum(cell_ns),
                    "min_cell_n": min(cell_ns),
                    "median_cell_n": round(st.median(cell_ns), 1),
                }
        b, w = res["by_model"][model].get("baseline"), res["by_model"][model].get("with_skill")
        if b and w:
            res["by_model"][model]["delta_pp"] = round(100 * (w["pass_rate"] - b["pass_rate"]), 1)
    return res


def render(res: dict, models: list[str]) -> str:
    pv = res.get("provenance", {})
    unguarded = sorted({m for m in models if not is_readonly(m)})
    total, ver = pv.get("runs", 0), pv.get("prompt_verified", 0)
    if total and ver == total:
        prov = f"All {total} runs answered the scenario prompts currently in the repository."
    elif total:
        bits = []
        if pv.get("no_prompt_sha"):
            bits.append(f"{pv['no_prompt_sha']} predate prompt-sha tracking")
        if pv.get("prompt_changed"):
            bits.append(f"{pv['prompt_changed']} answered a prompt that has since changed")
        prov = (f"**Provenance: {ver} of {total} runs verified against the current prompts** "
                f"({'; '.join(bits)}). Re-run to close the gap: the harness records a prompt "
                f"hash for every new run.")
    else:
        prov = "No timing data found, so provenance could not be established."

    # Any scenario a runtime cannot run is named in the report with its reason. Generated,
    # not written, so it cannot drift from NOT_RUNNABLE.
    holes = [(sc, m) for (sc, m) in NOT_RUNNABLE if m in models]
    if holes:
        prov += "\n"
        for sc, m in sorted(holes):
            prov += (f"\n> **`{sc}` was not runnable on {label(m)}.** {NOT_RUNNABLE[(sc, m)]} "
                     f"That column therefore covers "
                     f"{res['by_model'].get(m, {}).get('paired_scenarios', '?')} scenarios, not "
                     f"{len(res['scenarios'])}; its baseline and with-skill means are still "
                     f"averaged over the same set as each other.")

    # Any column short of the full suite for a reason NOT already documented above is named
    # here. agy's gap was disclosed because it is registered in NOT_RUNNABLE; Codex's was not,
    # and the table happily printed "12 scenarios" for both with an explanation for only one.
    # An undocumented hole reads as a complete column, which is how a smaller suite gets
    # mistaken for a comparable one.
    # poka-yoke: names any column short of the full suite, so a smaller scenario set cannot pass as a comparable one [warning]
    total_sc = len(res["scenarios"])
    for m in models:
        v = res["by_model"].get(m, {})
        paired = v.get("paired_scenarios")
        if paired is None or paired >= total_sc:
            continue
        explained = {sc for (sc, mm) in NOT_RUNNABLE if mm == m}
        missing = sorted(
            sc for sc, cells in res["scenarios"].items()
            if sc not in explained and not all(f"{m}_{c}" in cells for c in CONFIGS))
        if missing:
            prov += (f"\n\n> **{label(m)} is missing {', '.join('`'+x+'`' for x in missing)}.** "
                     f"Those cells were lost to repeated API rate limits and have not been "
                     f"re-collected. The column covers {paired} of {total_sc} scenarios; both "
                     f"of its arms are averaged over that same set, so its delta is "
                     f"like-for-like, but it is not directly comparable to a full column.")

    # The read-only guarantee is per-runner, so the report states which columns lack it.
    # Writing this by hand would mean remembering to, every time a runner is added.
    if unguarded:
        names = ", ".join(label(m) for m in unguarded)
        prov += (f"\n\n> **{names} runs were not structurally read-only.** Every other column "
                 f"was given a tool allowlist or a read-only sandbox, so writing was "
                 f"unrepresentable rather than merely discouraged. That CLI offers no "
                 f"equivalent, so its runs carry a weaker guarantee than the rest of this "
                 f"table.")

    L = ["# Poka-Yoke Benchmark", "",
         "Baseline vs with-skill, blind-graded against pre-written assertions.", "",
         prov, "",
         "## Summary", "",
         # `sd` is the spread of per-scenario pass rates, not a confidence interval on the
         # mean. Written as a bare "±" beside a percentage it reads as one, which claims a
         # precision this design cannot support: the scenarios differ in difficulty, so
         # their spread describes the suite, not the uncertainty in the number.
         "Spread is `sd`: the standard deviation of pass rates **across scenarios**. It "
         "describes how unevenly a model performs over the suite, and is *not* a confidence "
         "interval on the mean.", "",
         "| Model | Baseline | With skill | Delta | Mean time (base → skill) |",
         "|---|---|---|---|---|"]
    for m in models:
        d = res["by_model"].get(m, {})
        b, w = d.get("baseline"), d.get("with_skill")
        if b and w:
            L.append(f"| {label(m)} | {100*b['pass_rate']:.1f}% (sd {100*b['stdev']:.1f}) "
                     f"| {100*w['pass_rate']:.1f}% (sd {100*w['stdev']:.1f}) "
                     f"| **{d['delta_pp']:+.1f} pp** | {b['seconds']:.0f}s → {w['seconds']:.0f}s |")
    L += ["", "## Per scenario", "",
          "| Scenario | " + " | ".join(f"{label(m)}" for m in models) + " |",
          "|---" * (1 + len(models)) + "|",
          "| | " + " | ".join("base → skill" for _ in models) + " |"]
    for sid, cells in res["scenarios"].items():
        row = [f"`{sid}`"]
        for m in models:
            b, w = cells.get(f"{m}_baseline"), cells.get(f"{m}_with_skill")
            row.append(f"{100*b['pass_rate']:.0f}% → {100*w['pass_rate']:.0f}%" if b and w else ", ")
        L.append("| " + " | ".join(row) + " |")
    return "\n".join(L) + "\n"


def main() -> int:
    global BUDGET, PACE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--scenarios", nargs="+")
    ap.add_argument("--grader-model", default="claude-haiku-4-5-20251001",
                    help="checklist scoring is classification, not reasoning")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pace", type=float, default=1.0, help="seconds between calls")
    ap.add_argument("--max-calls", type=int, default=400, help="HARD ceiling; harness stops")
    ap.add_argument("--allow-narrower", action="store_true",
                    help="permit overwriting the published aggregate with one covering fewer "
                         "models or scenarios (refused by default)")
    ap.add_argument("--grade-only", action="store_true")
    ap.add_argument("--aggregate-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="report the call budget, do nothing")
    ap.add_argument("--preflight", action="store_true", help="check stored data for junk, then exit")
    ap.add_argument("--purge-suspect", action="store_true", help="with --preflight, delete what it finds")
    a = ap.parse_args()

    if a.preflight:
        return 0 if preflight(a.purge_suspect) == 0 else 1

    # Runs automatically. A pre-flight you have to remember is rung zero.
    if not a.aggregate_only and preflight(False) and not a.dry_run:
        print("\nRefusing to start on suspect data. Run --preflight --purge-suspect first.")
        return 2

    scenarios = json.loads((HERE / "scenarios.json").read_text())
    if a.scenarios:
        scenarios = [s for s in scenarios if s["id"] in a.scenarios]
    if not scenarios:
        print("no scenarios matched"); return 1

    run_jobs = [(sc, m, c, n) for sc in scenarios for m in a.models
                for c in CONFIGS for n in range(1, a.runs + 1)
                if (sc["id"], m) not in NOT_RUNNABLE]
    cells = [(sc, m, c) for sc in scenarios for m in a.models for c in CONFIGS
             if (sc["id"], m) not in NOT_RUNNABLE]
    def is_current(sc, m, c, n) -> bool:
        """A run counts as done only if it answered the current prompt: the same test
        do_run applies. Counting file existence alone under-reported the budget, which is
        the opposite of what a budget check is for."""
        d = run_dir(sc["id"], m, c, n)
        if not (d / "response.md").exists():
            return False
        try:
            return json.loads((d / "timing.json").read_text()).get("prompt_sha") == prompt_sha(sc)
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            return False

    # --aggregate-only reads what is already on disk and makes no model calls at all, so
    # counting work for it charged a budget that was never going to be spent, and the
    # refusal that followed is why the committed aggregate went stale: the only way past it
    # was to narrow to one model, which silently overwrote the full result with a partial one.
    todo_runs = 0 if (a.grade_only or a.aggregate_only) else sum(
        1 for j in run_jobs if not is_current(*j))
    # A cell needs a grading call if any of its runs is ungraded, INCLUDING runs that do
    # not exist yet and are about to be created. Counting only existing ungraded runs
    # under-reports the budget, which is the opposite of what a budget check is for.
    todo_cells = 0 if a.aggregate_only else sum(
        1 for sc, m, c in cells
        if any(not (run_dir(sc["id"], m, c, n) / "grading.json").exists()
               or not is_current(sc, m, c, n)
               for n in range(1, a.runs + 1)))

    print(f"== matrix: {len(scenarios)} scenarios x {len(a.models)} models x "
          f"{len(CONFIGS)} configs x {a.runs} runs ==")
    print(f"   runs to do:     {todo_runs:4} (of {len(run_jobs)}; rest already on disk)")
    print(f"   grade calls:    {todo_cells:4} (batched, one per cell)")
    print(f"   estimated total:{todo_runs + todo_cells:4} calls   budget ceiling {a.max_calls}")
    # A matrix of only high-limit runners can be driven much harder. Take the minimum
    # advertised concurrency across the models actually being run, so adding one Claude
    # column to a Codex sweep automatically drops the whole sweep back to safe pacing
    # rather than relying on whoever typed the command to remember.
    if a.workers == ap.get_default("workers"):
        caps = [RUNNERS[m]["workers"] for m in a.models if m in RUNNERS]
        if caps and len(caps) == len(a.models):
            a.workers = min(caps)
            print(f"   all runners are high-limit -> workers raised to {a.workers}, pacing off")
    # Report the pacing that will actually be used, per runner. Printing the global value
    # while run_cli silently applies a different one is the report-disagrees-with-code shape.
    paces = {label(m): RUNNERS.get(m, {}).get("pace", a.pace) for m in a.models}
    pace_txt = (f"{a.pace}s" if len(set(paces.values())) == 1 and a.pace in paces.values()
                else ", ".join(f"{k} {v}s" for k, v in paces.items()))
    print(f"   workers {a.workers}, pace {pace_txt}, grader {a.grader_model}", flush=True)
    if a.dry_run:
        return 0
    if todo_runs + todo_cells > a.max_calls:
        print(f"\nREFUSING: {todo_runs + todo_cells} calls exceeds --max-calls {a.max_calls}.\n"
              f"Raise the ceiling deliberately, or narrow --models/--scenarios/--runs.")
        return 2

    BUDGET, PACE = Budget(a.max_calls), a.pace

    try:
        if not a.aggregate_only:
            if not a.grade_only:
                with cf.ThreadPoolExecutor(a.workers) as ex:
                    futs = {ex.submit(do_run, *j): j for j in run_jobs}
                    for i, f in enumerate(cf.as_completed(futs), 1):
                        print(f"[{i:3}/{len(run_jobs)}] {f.result()}", flush=True)
            with cf.ThreadPoolExecutor(a.workers) as ex:
                futs = {ex.submit(grade_cell, sc, m, c, a.runs, a.grader_model): (sc, m, c)
                        for sc, m, c in cells}
                for i, f in enumerate(cf.as_completed(futs), 1):
                    print(f"[{i:3}/{len(cells)}] {f.result()}", flush=True)
    except BudgetExceeded as e:
        print(f"\nSTOPPED: {e}")

    res = aggregate(scenarios, a.models, a.runs)

    # A sweep aggregates only what IT ran. Running one model therefore rewrites the summary
    # as though the other three do not exist, which is exactly how the committed aggregate
    # came to describe four runs of one scenario while the README quoted 240. Say so loudly;
    # the fix is a final `--aggregate-only` across the full matrix once every chunk is done.
    prior = RESULTS / "benchmark.json"
    if prior.exists():
        try:
            was = json.loads(prior.read_text())
            lost_m = set(was.get("by_model", {})) - set(res.get("by_model", {}))
            lost_s = set(was.get("scenarios", {})) - set(res.get("scenarios", {}))
            # poka-yoke: refuses to overwrite a wider aggregate with a narrower one, so a partial result cannot replace a full one [control]
            #
            # This was a ::warning:: printed to stdout, and CLAUDE.md says in as many words
            # that it "went unread three times in one session" because the output was piped
            # through tail. It then happened a fourth time, during the review that produced
            # this change: a bare `--aggregate-only` zeroed every published pass rate and the
            # warning scrolled past above the tail window. A notice you can pipe away is not
            # a device. Refusing the write is.
            if lost_m or lost_s:
                if not a.allow_narrower:
                    print("\n✗ REFUSING TO WRITE: this aggregate is NARROWER than the one it "
                          "replaces.", file=sys.stderr)
                    if lost_m:
                        print(f"   models dropped:    {', '.join(sorted(lost_m))}", file=sys.stderr)
                    if lost_s:
                        print(f"   scenarios dropped: {', '.join(sorted(lost_s))}", file=sys.stderr)
                    print("\n   benchmark.json and benchmark.md were NOT modified.\n"
                          "   Re-run --aggregate-only over the full matrix, or pass\n"
                          "   --allow-narrower if you genuinely mean to publish a subset.",
                          file=sys.stderr)
                    return 2
                print("\n::warning:: writing a NARROWER aggregate because --allow-narrower "
                      "was passed.", file=sys.stderr)
        except (json.JSONDecodeError, OSError):
            pass
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "benchmark.json").write_text(json.dumps(res, indent=2))
    md = render(res, a.models)
    (RESULTS / "benchmark.md").write_text(md)
    print("\n" + md)
    if BUDGET:
        print(f"calls used: {BUDGET.used}/{BUDGET.limit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
