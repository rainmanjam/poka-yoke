# Releasing

A release here is one thing: **a git tag.** Every runtime installs from a git ref: the Claude Code
marketplace and every runtime with a native manifest, so there is no registry to keep in step with
the tag. Nothing is published to PyPI or npm; step 7 records why that is a choice rather than
an omission.

Read the honest note at the bottom before treating this as finished work.

---

## 0. Decide the version

One number governs everything. `plugins/poka-yoke/.claude-plugin/plugin.json` is the source
of truth; eleven other files carry it.

- **Patch**: a detector rule fixed, a doc corrected, a manifest field.
- **Minor**: a new skill, a new hazard rule, a new runtime, a new device template.
- **Major**: a skill removed or renamed, a CLI flag removed, a description rewritten enough
  to change routing. Renaming a skill breaks anyone invoking `/poka-yoke:<name>`.

Skill *content* changes are behaviour changes even when no interface moves. If routing or
output shifts, that is at least a minor.

## 1. Bump, and let the tooling propagate it

```bash
# edit "version" in plugins/poka-yoke/.claude-plugin/plugin.json, then:
python3 scripts/sync_platform_manifests.py
git diff --stat
```

You should see twelve files change: the one you edited and the eleven the script rewrote. If
you see one, you edited the wrong file. The whole point is that no manifest is updated by
hand.

```bash
python3 scripts/sync_platform_manifests.py --check   # must exit 0
```

## 2. Update the changelog

Move the `[Unreleased]` section under the new version heading with today's date. Say what
changed for a *user of the plugin*, not what changed in the repository.

## 3. Run everything locally

CI runs these too, but a failure here costs seconds and a failure after tagging means a
version that installed for whoever was quick, and a tag should not move.

```bash
python3 scripts/sync_platform_manifests.py --check
python3 tests/test_detector.py
python3 tests/test_skill_listing.py
python3 tests/test_portability.py
python3 plugins/poka-yoke/scripts/detect_hazards.py --paths plugins/ --severity high
python3 plugins/poka-yoke/scripts/device_registry.py --check --write docs/poka-yoke/registry.md
```

If the registry check fails you added a `poka-yoke:` marker comment. Regenerate with
`--write docs/poka-yoke/registry.md` (the same command without `--check`) and commit the
result.

## 4. Run the devices the way a user will

```bash
python3 plugins/poka-yoke/scripts/cli.py --help
python3 plugins/poka-yoke/scripts/cli.py detect --paths plugins/ --severity high
```

`cli.py` is executed as a plain file, so it must not depend on being installed. It briefly
did, via a package-relative import, and that only surfaced when running it outside a wheel.
`tests/test_portability.py` now checks it.

## 5. Land it on `main`

```bash
git switch -c release/vX.Y.Z
git add -A && git commit -m "release vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --fill
```

Wait for `validate.yml` to go green, every job. Merge.

## 6. Push the tag, which is the release

```bash
git switch main && git pull
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

`.github/workflows/release.yml` takes it from there:

| Job | What it does, and what it refuses |
|---|---|
| `guard` | Refuses the tag unless it matches `plugin.json`, `CHANGELOG.md` has a `## [X.Y.Z]` section, and the commit is an ancestor of `main`. Tagging v0.2.0 on a 0.1.0 tree would otherwise publish 0.1.0 under a 0.2.0 announcement. |
| `verify` | Calls `validate.yml`, the same workflow that guards pull requests. Not a copy of it; a copy eventually passes where the original would fail. |
| `github-release` | Notes come from the changelog section; an empty extraction fails the job rather than publishing a blank release. |

Every runtime installs from the git ref, so the tag *is* the release. There is nothing to
publish first and nothing that can be out of step with it.

## 7. Package registries, deliberately not used

The detector is not on PyPI or npm, and the skills invoke it by a path relative to the
SKILL.md that names it instead.

A published command would be better: `uvx <name> detect` resolves identically on every
runtime with no path at all. PyPI refuses it, and npm is expected to for the same reason:
each rejects a new name whose punctuation-stripped form matches an existing project, and
`pokayoke` is taken on both: registered on PyPI with zero releases, published on npm.
`poka-yoke` strips to `pokayoke` and collides. Only the PyPI refusal was observed; npm
applies its similarity check at publish time, so that row of the table is an expectation.

Checked 2026-08-21:

| Registry | Name | Status |
|---|---|---|
| PyPI | `poka-yoke` | refused: *"This project name is too similar to an existing project"* |
| PyPI | `pokayoke` | registered, **zero releases** (`/simple/` returns 200, the JSON API 404s) |
| npm | `poka-yoke` | unpublished (404); expected to be refused for the same reason, untested |
| npm | `pokayoke` | v0.0.7, maintainer `rorz`, first published 2026-06-04 (`npm view pokayoke`) |
| both | `poka-yoke-cli`, `poka-yoke-kit`, `poka-yoke-tools`, `mistakeproof` | free |

Note the trap in checking this: `https://pypi.org/pypi/<name>/json` returns 404 for a name
that is *registered but has no releases*, which is exactly the case here. Use
`https://pypi.org/simple/<name>/`; 200 means taken.

**If you want to revisit it**, the options are a suffixed name (free on both), or a PEP 541
request for `pokayoke` on PyPI, which has no releases and is a reasonable candidate for the
abandoned-name process. Whichever you choose, the distribution name and the console script
name must match, because `uvx NAME` resolves NAME as a distribution. A package called one
thing exposing a command called another cannot be run with `uvx` at all.

## 7b. When the repository goes public

**Upload the social preview.** Settings → General → Social preview →
`docs/assets/banner/github-social.png` (1280×640). This is the card that renders when the
repo link is pasted into Slack, X, Discord or an RSS reader; without it GitHub generates one
from the repo name and description.

It cannot be done before then. GitHub allows the upload on a public repository, or on a
private one that already had an image uploaded while it was public, and this repository has
always been private, so the control is not available yet. The image would not unfurl anyway:
only public repositories serve it.

**Add the four badges that need a public API.** shields.io reads the public GitHub API, so
each currently returns HTTP 200 with an error chip reading `repo not found`, which looks broken
rather than absent. Add them the day it goes public, not before:

```markdown
[![CI](https://img.shields.io/github/actions/workflow/status/rainmanjam/poka-yoke/validate.yml?label=CI)](https://github.com/rainmanjam/poka-yoke/actions/workflows/validate.yml)
[![release](https://img.shields.io/github/v/release/rainmanjam/poka-yoke)](https://github.com/rainmanjam/poka-yoke/releases)
[![last commit](https://img.shields.io/github/last-commit/rainmanjam/poka-yoke)](https://github.com/rainmanjam/poka-yoke/commits/main)
[![stars](https://img.shields.io/github/stars/rainmanjam/poka-yoke?style=flat)](https://github.com/rainmanjam/poka-yoke/stargazers)
```

The CI badge is the one worth having: it is the only badge on the page that is not a claim
this repository makes about itself. Add the release badge only after the first tag exists,
or it reads `no releases`.

## 8. Verify what a new user actually gets

Not what you think you shipped. What installs.

```bash
# Claude Code, from a scratch directory
claude plugin marketplace add rainmanjam/poka-yoke
claude plugin install poka-yoke@poka-yoke
claude plugin details poka-yoke        # 11 skills, version matches

# the detector, from what actually installed
python3 ~/.claude/plugins/*/poka-yoke/*/scripts/cli.py detect --paths .
```

Then open a session and invoke one skill by name. CI proves the install command works; only
this proves the skill loads and routes.

---

## If a release is wrong

**A tag can move, but should not.** Anyone who installed in between gets different content
under the same version. Cut a new patch instead.

**Delete a GitHub release** only if it was published within minutes and nothing consumed it.

Nothing here is irreversible in the way a package registry is: with no PyPI release to yank,
a bad version is corrected by the next tag.

---

## What is a device here, and what is still not

Steps 0–4 are backed by `--check` modes that fail. Steps 5–6 are backed by `release.yml`:
the tag guard, the reuse of `validate.yml` rather than a second copy of it, and failing on
an empty changelog extraction are enforced rather than remembered.

What remains training: **deciding the version** (step 0) and **noticing the changelog is
honest** (step 2). A machine can check that a `## [X.Y.Z]` section exists, and the guard does,
but not that it describes what actually changed. Step 8 is a human step by construction; its
whole purpose is to look at the thing rather than at a check about it.
