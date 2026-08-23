#!/usr/bin/env python3
"""Every GitHub Action must be pinned to a commit SHA, and every pin must still resolve.

`uses: actions/checkout@v5` runs whatever commit that label currently points at. The label
is mutable by the account that owns it, so a compromised maintainer account changes what
runs in this repository with no diff here for anyone to review. A 40-character SHA cannot be
repointed.

The cost of pinning is that pins rot: a fix published upstream never arrives. This reports
how far behind each pin is instead of pretending that problem away.

    python3 scripts/check_action_pins.py            # verify + report drift
    python3 scripts/check_action_pins.py --offline  # shape only, no network
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USES = re.compile(r"uses:\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)@(\S+?)(?:\s+#\s*(\S+))?\s*$", re.M)
SHA = re.compile(r"^[0-9a-f]{40}$")


def api(path: str):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={"User-Agent": "poka-yoke-pins", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> int:
    offline = "--offline" in sys.argv
    unpinned, stale, checked = [], [], 0

    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for repo, ref, comment in USES.findall(wf.read_text()):
            if repo.startswith("./"):
                continue
            checked += 1
            if not SHA.match(ref):
                unpinned.append(f"{wf.name}: {repo}@{ref} is a mutable label")
                continue
            if offline:
                continue
            try:
                head = api(f"repos/{repo}/commits/{comment or 'HEAD'}")["sha"]
            except Exception as e:                  # noqa: BLE001 - report, never crash CI
                print(f"  ? {repo}@{ref[:7]}, could not check ({e})")
                continue
            if head != ref:
                stale.append(f"{repo} pinned at {ref[:7]}, {comment or 'HEAD'} now {head[:7]}")
            print(f"  {'=' if head == ref else '~'} {repo}@{ref[:7]}"
                  f"{'' if head == ref else '  (behind)'}")

    if not checked:
        print("Found no actions at all: the probe is broken, not the workflows.",
              file=sys.stderr)
        return 2

    for s in stale:
        print(f"::warning::{s}")
    if unpinned:
        print(f"\n{len(unpinned)} unpinned action(s):", file=sys.stderr)
        for u in unpinned:
            print(f"  {u}", file=sys.stderr)
        print("\nPin to the commit SHA and leave the tag as a trailing comment.",
              file=sys.stderr)
        return 1

    print(f"\n✓ {checked} action reference(s), all pinned"
          + (f" · {len(stale)} behind upstream" if stale else " and current"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
