#!/usr/bin/env python3
"""Report the disposition of every review finding, and refuse to call the job done early.

103 findings is exactly the number where "I think I got most of them" starts sounding true.
Every finding gets one of three outcomes and none of them is silence:

  fixed     the copy changed
  rejected  the finding was checked and is wrong, or is taste rather than defect, with a reason
  deferred  real, but deliberately not now, with a reason

`--check` exits non-zero while anything is still open, so progress cannot be overstated.
"""
import json, sys, collections
from pathlib import Path

T = Path(__file__).resolve().parent.parent / ".review-work" / "triage.json"

def main() -> int:
    if not T.exists():
        print("no triage file, run the copy review first", file=sys.stderr); return 2
    items = json.loads(T.read_text())
    by = collections.Counter(i["status"] for i in items)
    print(f"  {len(items)} findings: " + "  ".join(f"{k}={v}" for k, v in sorted(by.items())))

    missing_reason = [i["n"] for i in items
                      if i["status"] in ("rejected", "deferred") and not i["note"].strip()]
    if missing_reason:
        print(f"  ✗ rejected/deferred without a reason: {missing_reason}", file=sys.stderr)

    if "--check" in sys.argv:
        if by.get("open"):
            files = collections.Counter(i["file"] for i in items if i["status"] == "open")
            print(f"\n  ✗ {by['open']} finding(s) still open:", file=sys.stderr)
            for f, n in files.most_common():
                print(f"      {n:3}  {f}", file=sys.stderr)
            return 1
        if missing_reason:
            return 1
        print("  ✓ every finding has a disposition")
    return 0

if __name__ == "__main__":
    sys.exit(main())
