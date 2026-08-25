#!/usr/bin/env python3
"""Track skills that have been vendored into somebody else's repository.

Some directories do not list a link to your skill, they take a copy of it. That copy is a
fork the moment you edit yours, and nothing anywhere announces it. It is the plainest
instance of the failure this project exists to argue about: the arrangement depends on
somebody remembering to go and refresh a file in a repository they do not work in.

So record what was shipped, and let a check fail when the source moves away from it.

    vendored_copies.py --check     # offline. Fails when our skill no longer matches what
                                   # was shipped downstream. This is the CI device.
    vendored_copies.py --online    # additionally fetch each downstream copy and confirm it
                                   # still matches. Catches edits made on their side.
    vendored_copies.py --update    # re-record after a refresh PR has been merged downstream

Only the body is compared, and the two sides are hashed separately.

`source_sha256` is our body as it stood when the copy was shipped; `downstream_sha256` is
their body as shipped. They are allowed to differ, because a directory may legitimately
require a section ours does not carry, and the alternative is editing a benchmarked skill to
suit a listing, which this project explicitly forbids without evidence. Two hashes keep both
questions answerable: have *we* moved since shipping, and have *they* edited their copy.

Frontmatter is excluded either way. Ours and theirs differ by design, so comparing whole
files would go red on the first line every time, and a check that cries wolf gets switched
off. A switched-off check is worse than none, because the absence is invisible.

The lock file is input, so it is treated as input: every path is confined to this repository
and every URL is confined to an allowlisted host before it is used. A device that fetches
whatever a JSON file tells it to is a hazard wearing the costume of a safety check.

Stdlib only, like everything else here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import re
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
LOCK = REPO / "vendored.lock.json"
TIMEOUT = 20

# A SKILL.md is tens of kilobytes. Reading without a ceiling means whatever the server sends
# is bought into memory, which this repository's own detector flags as F7 Unbounded read.
MAX_FETCH_BYTES = 1 << 20  # 1 MiB

# Downstream copies live on GitHub. Anything else in the lock is a mistake or an attack,
# and either way this script should not be the thing that fetches it.
ALLOWED_HOSTS = frozenset({"raw.githubusercontent.com"})


class LockError(Exception):
    """The lock file asked for something outside what this script is allowed to touch."""


# One path segment. A leading dot is allowed, because `.claude-plugin/plugin.json` and
# `.github/workflows/x.yml` are ordinary paths in this repository and the first version
# rejected them with "is not a plain name" — an error that is accurate about what it did and
# misleading about why, which sends the reader looking for a bug in the lock file.
#
# The negative lookahead is what keeps the traversal guarantee: "." and ".." are refused
# outright, so no combination of segments can climb out of the repository.
SEGMENT = re.compile(r"(?!\.{1,2}$)\.?[A-Za-z0-9][A-Za-z0-9._-]*")


def safe_source_path(rel: str) -> pathlib.Path:
    """Rebuild a repo-relative path from validated segments.

    The path is not merely checked and passed through, it is reconstructed from segments
    that each had to match SEGMENT. Nothing from the lock file reaches the filesystem
    except names that survived that, so ".." and absolute paths cannot be expressed rather
    than being detected and rejected.
    """
    segments = pathlib.PurePosixPath(rel).parts
    if not segments:
        raise LockError("source_path is empty")
    for segment in segments:
        if not SEGMENT.fullmatch(segment):
            raise LockError(f"source_path segment {segment!r} is not a plain name: {rel!r}")
    return REPO.joinpath(*segments)


def safe_url(raw: str) -> str:
    """Rebuild the URL from an allowlisted host and a validated path.

    As with safe_source_path, the input is not passed through once approved. The scheme is
    the literal "https", the host is the matching entry from ALLOWED_HOSTS rather than
    whatever was parsed, and the path must be plain. Query and fragment are dropped.
    """
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme != "https":
        raise LockError(f"raw_url must be https: {raw!r}")
    host = next((h for h in sorted(ALLOWED_HOSTS) if h == parts.hostname), None)
    if host is None:
        raise LockError(f"raw_url host {parts.hostname!r} is not allowlisted")
    if not re.fullmatch(r"(?:/[A-Za-z0-9][A-Za-z0-9._-]*)+", parts.path):
        raise LockError(f"raw_url path is not a plain file path: {parts.path!r}")
    return urllib.parse.urlunsplit(("https", host, parts.path, "", ""))


def body_of(text: str) -> str:
    """Everything after the YAML frontmatter, trailing whitespace normalised.

    Frontmatter is excluded deliberately: ours and theirs legitimately differ. Trailing
    whitespace is normalised because a downstream formatter that strips it would otherwise
    look identical to somebody rewriting the skill.
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[text.find("\n", end + 1) + 1:]
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def digest(text: str) -> str:
    return hashlib.sha256(body_of(text).encode("utf-8")).hexdigest()


def load() -> dict:
    if not LOCK.exists():
        return {"note": "Skills copied into third-party repositories, and the hash of the "
                        "body that was shipped. See scripts/vendored_copies.py.",
                "copies": []}
    return json.loads(LOCK.read_text())


def fetch(url: str) -> str | None:
    """Fetch an allowlisted URL, or None if it cannot be read.

    Only OSError is caught: URLError, HTTPError and TimeoutError are all subclasses of it,
    so naming them individually was redundant rather than thorough.
    """
    try:
        checked = safe_url(url)
    except LockError as exc:
        print(f"  ! {exc}", file=sys.stderr)
        return None
    req = urllib.request.Request(checked, headers={"User-Agent": "poka-yoke-vendored-check"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - scheme and host validated above
            # Read one byte past the ceiling so an oversized body is detectable rather than
            # silently truncated into something that would hash differently and be reported
            # as drift.
            body = resp.read(MAX_FETCH_BYTES + 1)
        if len(body) > MAX_FETCH_BYTES:
            print(f"  ! {url} returned more than {MAX_FETCH_BYTES} bytes; refusing to read it",
                  file=sys.stderr)
            return None
        return body.decode("utf-8")
    except OSError:
        return None


class Findings:
    """Tallies for one run, so the reporting cannot silently lose a category."""

    def __init__(self) -> None:
        self.problems: list[str] = []
        self.unverified: list[str] = []
        self.pending: list[str] = []
        self.checked = 0
        self.verified = 0


def _check_source(copy: dict, out: Findings) -> str | None:
    """Compare our current file against what was shipped. Returns the current digest."""
    try:
        src = safe_source_path(copy["source_path"])
    except LockError as exc:
        out.problems.append(str(exc))
        return None
    if not src.is_file():
        out.problems.append(
            f"{copy['source_path']} is gone, but it is vendored at "
            f"{copy['downstream_repo']}. Withdraw the copy or restore the file.")
        return None
    out.checked += 1
    now = digest(src.read_text(encoding="utf-8"))
    if now != copy["source_sha256"]:
        out.problems.append(
            f"{copy['source_path']} has changed since it was vendored into "
            f"{copy['downstream_repo']}.\n"
            f"      shipped {copy['source_sha256'][:12]}  now {now[:12]}\n"
            f"      Their copy is stale: {copy['downstream_url']}\n"
            f"      Open a refresh PR there, then run --update to re-record.")
    return now


def _check_downstream(copy: dict, out: Findings) -> None:
    """Fetch the downstream copy and compare it against what was shipped.

    An unreachable copy is recorded as unverified, never absorbed into success. The first
    version of this warned and then fell through to a line reading "downstream copies
    match", having compared nothing, which is the failure this whole script is about.
    """
    if copy.get("downstream_state") == "pending":
        # "Pending" is a claim about the world that stops being true without telling you.
        # Leaving a human to flip it is the rung-zero move this whole script argues against,
        # so try the fetch anyway: if it succeeds, the copy has landed and the lock is stale.
        landed = fetch(copy["raw_url"])
        if landed is None:
            out.pending.append(f"{copy['downstream_repo']} — not merged downstream yet, "
                               f"nothing to compare")
        else:
            matches = digest(landed) == copy["downstream_sha256"]
            out.problems.append(
                f"{copy['downstream_repo']} has MERGED the copy, but the lock still says "
                f"pending.\n"
                f"      The downstream body {'matches' if matches else 'DOES NOT match'} "
                f"what was recorded.\n"
                f"      Set downstream_state to \"live\" so --online starts verifying it"
                + ("." if matches else ", after reviewing what they changed."))
        return
    raw = fetch(copy["raw_url"])
    if raw is None:
        out.unverified.append(
            f"{copy['raw_url']}\n"
            f"      Could not be fetched. Network, or they moved or deleted it. Either "
            f"way this copy is UNVERIFIED, not confirmed.")
    elif digest(raw) != copy["downstream_sha256"]:
        out.problems.append(
            f"{copy['downstream_repo']} has edited their copy of {copy['source_path']} "
            f"since it was shipped.\n"
            f"      Review {copy['downstream_url']} before matching it.")
    else:
        out.verified += 1


def _summary(out: Findings, online: bool) -> str:
    noun = "copy" if out.checked == 1 else "copies"
    if not online:
        return (f"✓ {out.checked} vendored {noun} in sync "
                f"(offline: source unchanged since shipping)")
    tail = f", {len(out.pending)} not yet merged" if out.pending else ""
    return (f"✓ {out.checked} vendored {noun} unchanged locally; "
            f"{out.verified} confirmed identical downstream{tail}")


def _print_all(header: str, items: list[str]) -> None:
    print(header, file=sys.stderr)
    for item in items:
        print(f"    {item}", file=sys.stderr)


def _report(out: Findings, total: int, online: bool) -> int:
    # A check that verified nothing must not report success. Recording a copy and then
    # silently skipping it is precisely how this class of device stops working.
    if out.checked == 0 and total:
        print("✗ recorded vendored copies exist but none could be checked", file=sys.stderr)
        return 2
    if out.problems:
        _print_all("✗ vendored copies have drifted:", out.problems)
        return 1
    for note in out.pending:
        print(f"  · {note}")
    if out.unverified:
        _print_all(
            f"⚠ {out.checked} cop{'y' if out.checked == 1 else 'ies'} match locally, but "
            f"{len(out.unverified)} could not be verified downstream:", out.unverified)
        return 2
    print(_summary(out, online))
    return 0


def cmd_check(online: bool) -> int:
    copies = load().get("copies", [])
    if not copies:
        print("no vendored copies recorded; nothing to check")
        return 0
    out = Findings()
    for copy in copies:
        if _check_source(copy, out) is not None and online:
            _check_downstream(copy, out)
    return _report(out, len(copies), online)


def cmd_update() -> int:
    """Re-record a copy after a downstream refresh has actually merged.

    The first version rewrote `source_sha256` and nothing else. `downstream_sha256` was read
    in two places and written in none, so the first time anyone followed the instruction this
    script prints — "open a refresh PR there, then run --update to re-record" — the downstream
    hash stayed at its original value and `--online` reported "they have edited their copy"
    for ever after. The docstring at the top of this file says a check that cries wolf gets
    switched off; that is how it would have started.

    So the two sides are re-recorded together, from the copy that is actually published. A
    successful fetch is also proof the copy has landed, which is what flips `downstream_state`
    off "pending" — the flip used to be a hand edit to JSON, which is rung zero sitting inside
    a device built to argue against rung zero.
    """
    reg = load()
    copies = reg.get("copies", [])
    if not copies:
        print("no vendored copies recorded; nothing to update")
        return 0

    changed, failed = [], []
    for copy in copies:
        try:
            src = safe_source_path(copy["source_path"])
        except LockError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        if not src.is_file():
            failed.append(f"{copy['source_path']} is missing; refusing to re-record it")
            continue

        raw = fetch(copy["raw_url"])
        if raw is None:
            # Recording our side alone would assert the two are in step when the downstream
            # half was never read. A half-written lock is worse than an unwritten one,
            # because the next --online believes it.
            failed.append(f"{copy['downstream_repo']}: could not fetch {copy['raw_url']}. "
                          f"Nothing re-recorded for this copy.")
            continue

        before = (copy.get("source_sha256"), copy.get("downstream_sha256"),
                  copy.get("downstream_state"))
        copy["source_sha256"] = digest(src.read_text(encoding="utf-8"))
        copy["downstream_sha256"] = digest(raw)
        copy["downstream_state"] = "live"
        if (copy["source_sha256"], copy["downstream_sha256"], copy["downstream_state"]) != before:
            changed.append(copy)

    if failed:
        print("✗ nothing was written:", file=sys.stderr)
        for f in failed:
            print(f"    {f}", file=sys.stderr)
        return 2

    LOCK.write_text(json.dumps(reg, indent=1, sort_keys=True) + "\n")
    if changed:
        print("re-recorded:")
        for copy in changed:
            print(f"    {copy['downstream_repo']}")
            print(f"      source     {copy['source_sha256'][:12]}")
            print(f"      downstream {copy['downstream_sha256'][:12]}")
            print(f"      state      {copy['downstream_state']}")
        print("\nOnly run this AFTER the downstream refresh has actually merged. Running it "
              "first records their OLD body as current and disarms the comparison.")
    else:
        print("nothing to update; both hashes already match what is published")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true",
                       help="offline drift check (the CI device)")
    group.add_argument("--online", action="store_true",
                       help="also fetch and compare each downstream copy")
    group.add_argument("--update", action="store_true",
                       help="re-record hashes after a merged downstream refresh")
    args = ap.parse_args()
    try:
        return cmd_update() if args.update else cmd_check(online=args.online)
    except LockError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
