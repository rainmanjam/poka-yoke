#!/usr/bin/env python3
"""Single entry point for poka-yoke's executable devices.

    python3 scripts/cli.py detect --diff
    python3 scripts/cli.py registry --check

The tools can also be run directly, `detect_hazards.py` and `device_registry.py`: which is
the convenient form in a pre-commit hook or a CI step. This dispatcher exists so a skill can
name one path instead of remembering which file holds which tool.

There is no packaging here on purpose. Publishing to PyPI would let skills invoke a command
that resolves identically on every runtime, but both PyPI and npm refuse a new name whose
punctuation-stripped form matches an existing project, and `pokayoke` is taken on both. That
is revisitable; see RELEASING.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

VERSION = "0.2.0"

USAGE = """usage: cli.py <command> [options]

commands:
  detect      scan for hazards, shapes in code that make mistakes easy
  registry    generate or check the device registry

Run `cli.py <command> --help` for that command's options.

  python3 scripts/cli.py detect --diff               scan uncommitted changes
  python3 scripts/cli.py detect --paths src/ --json  scan specific paths
  python3 scripts/cli.py registry --check            CI: fail if the registry is stale
"""


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if argv[0] in ("-V", "--version"):
        print(VERSION)
        return 0

    cmd, rest = argv[0], argv[1:]
    # Rewrite argv so each tool's own argparse reports the subcommand in its usage line,
    # rather than the name of the file it happens to live in.
    if cmd == "detect":
        from detect_hazards import main as run
        sys.argv = ["cli.py detect", *rest]
        return run()
    if cmd == "registry":
        from device_registry import main as run
        sys.argv = ["cli.py registry", *rest]
        return run()

    print(f"cli.py: unknown command {cmd!r}\n", file=sys.stderr)
    print(USAGE, end="", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
