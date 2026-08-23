#!/usr/bin/env python3
"""Fan one question out to three different models and reconcile what comes back.

Opus, Antigravity and Codex are different models with different training and different
blind spots. Asking all three and keeping only what survives reconciliation is worth more
than asking the best one twice: a second opinion from the same model tends to agree with
the first, which feels like corroboration and is not.

Fable does the reconciliation rather than one of the three reviewers, so no reviewer grades
its own work.

This module is the shared machinery. `review_copy.py` and `find_outreach.py` are thin
entry points on top of it.

Design notes that were learned the hard way, in this order:
  * `agy -p` takes the NEXT argv item as its prompt, so any other flag must come first.
  * `codex exec` refuses to run outside a git repository unless told otherwise.
  * Prompt bodies go in a file, not in argv: a review unit runs to tens of kilobytes and
    ARG_MAX is not somewhere to find your limits.
  * Every call costs real money at a third-party vendor, so there is a hard ceiling and a
    dry run that reports the bill before spending it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Reviewer:
    name: str
    argv: tuple                      # {prompt} is substituted
    timeout: int = 900

    def command(self, prompt: str) -> list[str]:
        return [a.replace("{prompt}", prompt).replace("{repo}", str(REPO)) for a in self.argv]


OPUS = Reviewer("opus", ("claude", "-p", "--model", "claude-opus-5", "{prompt}"))
AGY = Reviewer("agy", ("agy", "--dangerously-skip-permissions", "-p", "{prompt}"))
CODEX = Reviewer("codex", ("codex", "exec", "--sandbox", "read-only", "-C", "{repo}", "{prompt}"))
SONNET = Reviewer("sonnet", ("claude", "-p", "--model", "claude-sonnet-5", "{prompt}"))
FABLE = Reviewer("fable", ("claude", "-p", "--model", "claude-fable-5", "{prompt}"))

PANEL = (OPUS, AGY, CODEX)


@dataclass
class Task:
    """One unit of work: a name, a body to reason about, and what to do with it."""
    key: str
    instruction: str
    body: str = ""
    body_name: str = "input.md"
    _path: Path | None = field(default=None, repr=False)

    def materialise(self, workdir: Path) -> str:
        """Write the body beside the prompt and return the instruction that points at it."""
        if not self.body:
            return self.instruction
        d = workdir / self.key
        d.mkdir(parents=True, exist_ok=True)
        self._path = d / self.body_name
        self._path.write_text(self.body)
        return f"{self.instruction}\n\nThe material to work from is the file:\n{self._path}\n"


# ------------------------------------------------------------------ running

def run_one(rev: Reviewer, prompt: str) -> tuple[str, str | None]:
    """Return (stdout, error). Never raises: one dead reviewer must not sink the run."""
    try:
        r = subprocess.run(rev.command(prompt), capture_output=True, text=True,
                           timeout=rev.timeout, cwd=REPO)
    except subprocess.TimeoutExpired:
        return "", f"timed out after {rev.timeout}s"
    except FileNotFoundError:
        return "", f"{rev.name} is not installed"
    if r.returncode != 0 and not r.stdout.strip():
        return "", (r.stderr or "").strip()[:200] or f"exit {r.returncode}"
    return r.stdout, None


JSON_BLOCK = re.compile(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", re.S)


def extract_json(text: str):
    """Pull the findings out of whatever the model wrapped them in.

    Models add preamble, fence the block, or apologise first. Failing to parse is reported
    rather than swallowed: a reviewer whose output silently became an empty list would look
    exactly like a reviewer that found nothing.
    """
    if not text.strip():
        return None, "empty output"
    m = JSON_BLOCK.search(text)
    if m:
        try:
            return json.loads(m.group(1)), None
        except json.JSONDecodeError as e:
            return None, f"fenced block is not valid JSON: {e}"
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1]), None
            except json.JSONDecodeError:
                continue
    return None, "no JSON found in output"


def fan_out(tasks: list[Task], reviewers=PANEL, workers: int = 6,
            workdir: Path | None = None, on_event=print) -> list[dict]:
    """Run every (task x reviewer) pair concurrently. Returns one record per pair."""
    tmp = workdir or Path(tempfile.mkdtemp(prefix="fanout-"))
    prompts = {t.key: t.materialise(tmp) for t in tasks}
    jobs = [(t, rev) for t in tasks for rev in reviewers]
    out: list[dict] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_one, rev, prompts[t.key]): (t, rev) for t, rev in jobs}
        for fut in as_completed(futures):
            t, rev = futures[fut]
            raw, err = fut.result()
            findings, perr = (None, err) if err else extract_json(raw)
            rec = {"task": t.key, "reviewer": rev.name, "error": err or perr,
                   "findings": findings if isinstance(findings, list) else
                               ([findings] if findings else []),
                   "raw_chars": len(raw)}
            out.append(rec)
            mark = "OK " if not rec["error"] else "ERR"
            on_event(f"  {mark} {t.key:22} {rev.name:6} "
                     f"{len(rec['findings']):3} finding(s)"
                     + (f"  [{rec['error']}]" if rec["error"] else ""))
    return out


def synthesise(instruction: str, payload, workdir: Path | None = None):
    """Hand everything to Fable to reconcile. Returns (parsed, raw, error)."""
    tmp = workdir or Path(tempfile.mkdtemp(prefix="fanout-syn-"))
    tmp.mkdir(parents=True, exist_ok=True)
    p = tmp / "findings.json"
    p.write_text(json.dumps(payload, indent=2))
    raw, err = run_one(FABLE, f"{instruction}\n\nThe findings to reconcile are in:\n{p}\n")
    if err:
        return None, raw, err
    parsed, perr = extract_json(raw)
    return parsed, raw, perr


def budget_guard(n_calls: int, max_calls: int, dry_run: bool, on_event=print) -> bool:
    """Report the bill before spending it. Returns True if the caller should stop.

    Three vendors, real money, and a loop that is easy to widen by accident. The ceiling is
    deliberate rather than advisory: raising it is a decision someone makes on purpose.
    """
    on_event(f"  planned calls: {n_calls}   ceiling: {max_calls}")
    if dry_run:
        on_event("  dry run, nothing was spent.")
        return True
    if n_calls > max_calls:
        on_event(f"\nREFUSING: {n_calls} calls exceeds --max-calls {max_calls}.\n"
                 f"Raise the ceiling deliberately, or narrow the scope.")
        return True
    return False
