#!/usr/bin/env python3
"""Generate every platform manifest from one source of truth.

poka-yoke ships to many runtimes, each wanting its own manifest with the same name, version,
description and keywords in a slightly different shape. Nine hand-maintained copies is nine
chances to update eight of them, and the failure is silent, because each file stays
individually valid while disagreeing with the others. That is precisely the drift that broke
the documented install command once already.

So the Claude plugin manifest is the source of truth and the rest are derived. `--check`
recomputes them and fails if anything on disk has drifted, which is what makes this a device
rather than a convention.

    python3 scripts/sync_platform_manifests.py            # write
    python3 scripts/sync_platform_manifests.py --check    # CI: fail if stale

Standard library only, so it runs anywhere the detector runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "poka-yoke"
SOURCE = PLUGIN / ".claude-plugin" / "plugin.json"

# Where the skills live, relative to each manifest that names them.
SKILLS_FROM_PLUGIN = "./skills/"

def load_source() -> dict:
    if not SOURCE.exists():
        sys.exit(f"source of truth missing: {SOURCE}")
    return json.loads(SOURCE.read_text())


def j(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build(src: dict) -> dict[Path, str]:
    """Return {path: exact expected content} for every derived file."""
    name = src["name"]
    ver = src["version"]
    desc = src["description"]
    author = src.get("author", {})
    home = src.get("homepage", "")
    repo = src.get("repository", "")
    lic = src.get("license", "MIT")
    kw = src.get("keywords", [])
    # The listing description is long by design; manifests that show it in a card want the
    # short form, so take the first sentence rather than inventing a second wording.
    short = desc.split(".")[0].strip() + "."

    common = {
        "name": name,
        "version": ver,
        "description": desc,
        "author": author,
        "homepage": home,
        "repository": repo,
        "license": lic,
        "keywords": kw,
        "skills": SKILLS_FROM_PLUGIN,
    }

    out: dict[Path, str] = {}

    # --- Codex ---------------------------------------------------------------
    codex = dict(common)
    codex["hooks"] = {}
    codex["interface"] = {
        "displayName": src.get("displayName", name),
        "shortDescription": short,
        "longDescription": desc,
        "developerName": author.get("name", ""),
        "category": "Developer Tools",
        "capabilities": ["Interactive", "Read", "Write"],
        "defaultPrompt": [
            "Audit this module for mistakes that are possible.",
            "Design this API so the wrong call cannot be written.",
        ],
        "websiteURL": home,
    }
    out[PLUGIN / ".codex-plugin" / "plugin.json"] = j(codex)

    # --- Cursor --------------------------------------------------------------
    cursor = {
        "name": name,
        "displayName": src.get("displayName", name),
        "description": short,
        "version": ver,
        "author": author,
        "homepage": home,
        "repository": repo,
        "license": lic,
        "keywords": kw,
        "skills": SKILLS_FROM_PLUGIN,
    }
    out[PLUGIN / ".cursor-plugin" / "plugin.json"] = j(cursor)

    # --- Runtimes that read a plain plugin.json --------------------------------
    # Grok, Qoder and Kiro were added after seeing DietrichGebert/ponytail ship them; the
    # marginal cost here is zero because every one of these files is generated, and the
    # marginal claim is honest because docs/install.md files them under the tier that says
    # "structurally verified, not behaviourally tested".
    for d in (".devin-plugin", ".kimi-plugin", ".grok-plugin", ".qoder-plugin", ".kiro"):
        out[PLUGIN / d / "plugin.json"] = j(dict(common))

    # --- Plugin root, which is what the Agent Plugins v1.0.0 spec expects -------
    # GitHub's awesome-copilot intake looks for plugin.json at `.github/plugin/`,
    # `.plugin/`, or the plugin root, in that order, and warns unless it is at the root.
    # `.claude-plugin/plugin.json` is not among them, so their install smoke test found
    # no manifest at all and both that gate and the version-match gate failed. Generated
    # like every other platform manifest rather than hand-written, so the existing
    # `--check` is what stops it drifting from the canonical source.
    out[PLUGIN / "plugin.json"] = j(dict(common))

    # --- Hermes (YAML, hand-emitted so we stay dependency-free) --------------
    out[PLUGIN / ".hermes-plugin" / "plugin.yaml"] = (
        f"name: {name}\n"
        f"version: {ver}\n"
        f"description: {short}\n"
        f"author: {author.get('name', '')}\n"
        f"skills: {SKILLS_FROM_PLUGIN}\n"
    )

    # --- .agents (cross-runtime marketplace: Codex, Copilot CLI, Gemini CLI) -
    out[ROOT / ".agents" / "plugins" / "marketplace.json"] = j({
        "name": name,
        "interface": {"displayName": src.get("displayName", name)},
        "plugins": [{
            "name": name,
            "source": {"source": "url", "url": "./"},
            "policy": {"installation": "AVAILABLE", "authentication": "NONE"},
            "category": "Developer Tools",
        }],
    })

    # --- Gemini CLI extension -------------------------------------------------
    out[ROOT / "gemini-extension.json"] = j({
        "name": name,
        "description": short,
        "version": ver,
        "contextFileName": "GEMINI.md",
    })

    # No npm package: publishing is on hold. Pi and opencode read `pi.skills` from a
    # package.json, so they lose their declarative install until that returns, vendoring
    # the skills directory still works. See RELEASING.md.

    # --- Codex slash commands ---------------------------------------------------
    # Three of the four neighbouring projects surveyed ship these and poka-yoke did not, so
    # Codex users had the skills but no way to invoke a mode by name. Generated from the
    # skills themselves: a command that names a skill which no longer exists is not a
    # possible state.
    for name, summary in sorted(skill_summaries().items()):
        # The router is `/poka-yoke`, not `/poka-yoke-poka-yoke`.
        cmd = "poka-yoke" if name == "poka-yoke" else f"poka-yoke-{name}"
        out[ROOT / "commands" / f"{cmd}.toml"] = (
            f'description = "{summary}"\n'
            f'prompt = "Load the poka-yoke `{name}` skill from '
            f'plugins/poka-yoke/skills/{name}/SKILL.md and follow it for this request. '
            f'Classify what happens when the mistake occurs and how the device notices, '
            f'then propose the strongest device that prevents it and say which rung it '
            f'reaches. If the request does not fit this mode, say so in one line and hand '
            f'off to the mode that does."\n')

    return out


def skill_summaries() -> dict:
    """First sentence of each skill's description, short enough for a command palette."""
    out = {}
    for d in sorted(p for p in (PLUGIN / "skills").iterdir() if p.is_dir()):
        txt = (d / "SKILL.md").read_text()
        m = (re.search(r"^description:\s*>-?\s*\n((?:[ \t]+.*\n)+)", txt, re.M)
             or re.search(r"^description:\s*(.+)$", txt, re.M))
        desc = " ".join(m.group(1).split()) if m else d.name
        first = desc.split(". ")[0].strip().rstrip(".")
        first = first.replace('"', "'")
        if len(first) > 110:                    # cut at a word, not mid-"signature"
            first = first[:110].rsplit(" ", 1)[0].rstrip(",;:, -") + "…"
        out[d.name] = first
    return out


def sync_versions(ver: str, check: bool) -> list[str]:
    """Version lives in files this generator does not own outright. Keep it honest."""
    stale = []

    mkt = ROOT / ".claude-plugin" / "marketplace.json"
    if mkt.exists():
        d = json.loads(mkt.read_text())
        touched = False
        if d.get("metadata", {}).get("version") != ver:
            d.setdefault("metadata", {})["version"] = ver
            touched = True
        for p in d.get("plugins", []):
            if p.get("version") != ver:
                p["version"] = ver
                touched = True
        if touched:
            stale.append(str(mkt.relative_to(ROOT)))
            if not check:
                mkt.write_text(j(d))

    cli = PLUGIN / "scripts" / "cli.py"
    if cli.exists():
        t = cli.read_text()
        new = re.sub(r'(?m)^VERSION = "[^"]*"', f'VERSION = "{ver}"', t, count=1)
        if new != t:
            stale.append(str(cli.relative_to(ROOT)))
            if not check:
                cli.write_text(new)

    return stale


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="fail if any derived file has drifted (does not write)")
    args = ap.parse_args()

    src = load_source()
    want = build(src)
    stale = []

    for path, content in want.items():
        have = path.read_text() if path.exists() else None
        if have != content:
            stale.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

    stale += sync_versions(src["version"], args.check)

    if args.check:
        if stale:
            print("These derived files have drifted from "
                  f"{SOURCE.relative_to(ROOT)}:", file=sys.stderr)
            for s in stale:
                print(f"  {s}", file=sys.stderr)
            print("\nRun: python3 scripts/sync_platform_manifests.py", file=sys.stderr)
            return 1
        # `+ 3` was a hard-coded guess at how many files carry the version, and it
        # drifted the moment that set changed. Count them instead.
        n_version = len(sync_versions(src["version"], check=True))
        print(f"✓ {len(want) + n_version} derived files match "
              f"{SOURCE.relative_to(ROOT)}")
        return 0

    if stale:
        for s in stale:
            print(f"  wrote {s}")
    print(f"\n{len(stale)} file(s) updated · {len(want)} manifests derived from "
          f"{SOURCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
