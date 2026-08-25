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

Only the body is compared. The downstream copy carries its own frontmatter (their `category`,
`risk`, `source_repo` fields), so comparing whole files would fail on the first line every
time and the check would be discarded as noise within a week. A check that cries wolf gets
switched off, and a check that is switched off is worse than none, because the absence is
invisible.

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
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
LOCK = REPO / "vendored.lock.json"
TIMEOUT = 20

# Downstream copies live on GitHub. Anything else in the lock is a mistake or an attack,
# and either way this script should not be the thing that fetches it.
ALLOWED_HOSTS = frozenset({"raw.githubusercontent.com"})


class LockError(Exception):
    """The lock file asked for something outside what this script is allowed to touch."""


def safe_source_path(rel: str) -> pathlib.Path:
    """Resolve a lock-file path, refusing anything that escapes the repository."""
    if pathlib.PurePosixPath(rel).is_absolute() or "\\" in rel:
        raise LockError(f"source_path must be repo-relative and POSIX-style: {rel!r}")
    resolved = (REPO / rel).resolve()
    if resolved != REPO and REPO not in resolved.parents:
        raise LockError(f"source_path escapes the repository: {rel!r}")
    return resolved


def safe_url(raw: str) -> str:
    """Return the URL only if it is https and on an allowlisted host."""
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme != "https":
        raise LockError(f"raw_url must be https: {raw!r}")
    if parts.hostname not in ALLOWED_HOSTS:
        raise LockError(f"raw_url host {parts.hostname!r} is not allowlisted")
    return raw


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
            return resp.read().decode("utf-8")
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
    if now != copy["shipped_sha256"]:
        out.problems.append(
            f"{copy['source_path']} has changed since it was vendored into "
            f"{copy['downstream_repo']}.\n"
            f"      shipped {copy['shipped_sha256'][:12]}  now {now[:12]}\n"
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
        out.pending.append(f"{copy['downstream_repo']} — not merged downstream yet, "
                           f"nothing to compare")
        return
    raw = fetch(copy["raw_url"])
    if raw is None:
        out.unverified.append(
            f"{copy['raw_url']}\n"
            f"      Could not be fetched. Network, or they moved or deleted it. Either "
            f"way this copy is UNVERIFIED, not confirmed.")
    elif digest(raw) != copy["shipped_sha256"]:
        out.problems.append(
            f"{copy['downstream_repo']} has edited their copy of {copy['source_path']} "
            f"since it was shipped.\n"
            f"      Review {copy['downstream_url']} before matching it.")
    else:
        out.verified += 1


def _report(out: Findings, total: int, online: bool) -> int:
    # A check that verified nothing must not report success. Recording a copy and then
    # silently skipping it is precisely how this class of device stops working.
    if out.checked == 0 and total:
        print("✗ recorded vendored copies exist but none could be checked", file=sys.stderr)
        return 2
    if out.problems:
        print("✗ vendored copies have drifted:", file=sys.stderr)
        for problem in out.problems:
            print(f"    {problem}", file=sys.stderr)
        return 1
    for note in out.pending:
        print(f"  · {note}")
    if out.unverified:
        print(f"⚠ {out.checked} cop{'y' if out.checked == 1 else 'ies'} match locally, but "
              f"{len(out.unverified)} could not be verified downstream:", file=sys.stderr)
        for item in out.unverified:
            print(f"    {item}", file=sys.stderr)
        return 2
    noun = "copy" if out.checked == 1 else "copies"
    if online:
        tail = f", {len(out.pending)} not yet merged" if out.pending else ""
        print(f"✓ {out.checked} vendored {noun} unchanged locally; "
              f"{out.verified} confirmed identical downstream{tail}")
    else:
        print(f"✓ {out.checked} vendored {noun} in sync "
              f"(offline: source unchanged since shipping)")
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
    reg = load()
    changed = []
    for copy in reg.get("copies", []):
        try:
            src = safe_source_path(copy["source_path"])
        except LockError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        if not src.is_file():
            continue
        now = digest(src.read_text(encoding="utf-8"))
        if now != copy["shipped_sha256"]:
            changed.append((copy["source_path"], copy["shipped_sha256"], now))
            copy["shipped_sha256"] = now
    LOCK.write_text(json.dumps(reg, indent=1, sort_keys=True) + "\n")
    if changed:
        print("re-recorded:")
        for path, old, new in changed:
            print(f"    {path}  {old[:12]} -> {new[:12]}")
        print("\nOnly run this AFTER the downstream refresh has actually merged. Running "
              "it first is how the check gets quietly disarmed.")
    else:
        print("nothing to update; every recorded hash already matches")
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
