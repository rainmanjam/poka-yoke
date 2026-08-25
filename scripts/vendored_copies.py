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

Stdlib only, like everything else here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
LOCK = REPO / "vendored.lock.json"
TIMEOUT = 20


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
    req = urllib.request.Request(url, headers={"User-Agent": "poka-yoke-vendored-check"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed https URL from the lock
            return r.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def cmd_check(online: bool) -> int:
    reg = load()
    copies = reg.get("copies", [])
    if not copies:
        print("no vendored copies recorded; nothing to check")
        return 0

    problems, checked = [], 0
    unverified, pending, verified = [], [], 0
    for c in copies:
        src = REPO / c["source_path"]
        if not src.exists():
            problems.append(f"{c['source_path']} is gone, but it is vendored at "
                            f"{c['downstream_repo']}. Withdraw the copy or restore the file.")
            continue
        checked += 1
        now = digest(src.read_text(encoding="utf-8"))
        if now != c["shipped_sha256"]:
            problems.append(
                f"{c['source_path']} has changed since it was vendored into "
                f"{c['downstream_repo']}.\n"
                f"      shipped {c['shipped_sha256'][:12]}  now {now[:12]}\n"
                f"      Their copy is stale: {c['downstream_url']}\n"
                f"      Open a refresh PR there, then run --update to re-record.")

        if online:
            # The first version of this branch printed a warning when the fetch failed and
            # then fell through to the success line, which said "downstream copies match".
            # It had checked nothing. That is the shape this repository exists to catch, so
            # an unreachable copy is now counted and reported, never absorbed.
            if c.get("downstream_state") == "pending":
                pending.append(f"{c['downstream_repo']} — not merged downstream yet, "
                               f"nothing to compare")
            else:
                raw = fetch(c["raw_url"])
                if raw is None:
                    unverified.append(
                        f"{c['raw_url']}\n"
                        f"      Could not be fetched. Network, or they moved or deleted it. "
                        f"Either way this copy is UNVERIFIED, not confirmed.")
                elif digest(raw) != c["shipped_sha256"]:
                    problems.append(
                        f"{c['downstream_repo']} has edited their copy of "
                        f"{c['source_path']} since it was shipped.\n"
                        f"      Review {c['downstream_url']} before matching it.")
                else:
                    verified += 1

    # A check that verified nothing must not report success. Recording a copy and then
    # silently skipping it is precisely how this class of device stops working.
    if checked == 0 and copies:
        print("✗ recorded vendored copies exist but none could be checked", file=sys.stderr)
        return 2

    if problems:
        print("✗ vendored copies have drifted:", file=sys.stderr)
        for pr in problems:
            print(f"    {pr}", file=sys.stderr)
        return 1

    for note in pending:
        print(f"  · {note}")

    if unverified:
        # Not a drift failure, but emphatically not a pass either. Reporting these as
        # success is how a check quietly stops being one.
        print(f"⚠ {checked} cop{'y' if checked == 1 else 'ies'} match locally, but "
              f"{len(unverified)} could not be verified downstream:", file=sys.stderr)
        for u in unverified:
            print(f"    {u}", file=sys.stderr)
        return 2

    if online:
        print(f"✓ {checked} vendored cop{'y' if checked == 1 else 'ies'} unchanged locally; "
              f"{verified} confirmed identical downstream"
              f"{f', {len(pending)} not yet merged' if pending else ''}")
    else:
        print(f"✓ {checked} vendored cop{'y' if checked == 1 else 'ies'} in sync "
              f"(offline: source unchanged since shipping)")
    return 0


def cmd_update() -> int:
    reg = load()
    changed = []
    for c in reg.get("copies", []):
        src = REPO / c["source_path"]
        if not src.exists():
            continue
        now = digest(src.read_text(encoding="utf-8"))
        if now != c["shipped_sha256"]:
            changed.append((c["source_path"], c["shipped_sha256"], now))
            c["shipped_sha256"] = now
    LOCK.write_text(json.dumps(reg, indent=1, sort_keys=True) + "\n")
    if not changed:
        print("nothing to update; every recorded hash already matches")
        return 0
    print("re-recorded:")
    for path, old, new in changed:
        print(f"    {path}  {old[:12]} -> {new[:12]}")
    print("\nOnly run this AFTER the downstream refresh has actually merged. Running it "
          "first is how the check gets quietly disarmed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="offline drift check (the CI device)")
    g.add_argument("--online", action="store_true", help="also fetch and compare each copy")
    g.add_argument("--update", action="store_true", help="re-record hashes after a merged refresh")
    a = ap.parse_args()
    if a.update:
        return cmd_update()
    return cmd_check(online=a.online)


if __name__ == "__main__":
    sys.exit(main())
