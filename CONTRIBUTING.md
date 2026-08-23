# Contributing

## The bar for a new hazard

A hazard entry in `plugins/poka-yoke/references/hazard-catalog.md` needs all four of these.
Entries missing any of them dilute the catalog, which is the main way a resource like this
loses its value.

1. **A specific wrong action** a person can take, stated as an action rather than as a quality.
   "A caller can pass the order ID where the account ID belongs," not "the types are weak."
2. **A consequence**, including whether it is *silent*. Silence is the aggravator: a mistake
   that throws immediately is far less dangerous than one that returns a plausible wrong answer.
3. **A device** that closes it: a concrete change, not advice.
4. **An honest rung.** Control, Warning, or Detection. If your device is Warning, say what
   Control would have required. Overclaiming Control is the one thing that makes this method
   worse than no method, because it produces confidence without protection.

If you cannot name the wrong action, it is a style preference, not a hazard.

Use the next free ID in the relevant lens (`C` contact, `F` fixed-value, `M` motion-step,
`X` removed-device) and add it to the table of contents.

## Adding a detector rule

Rules live in `RULES` in `plugins/poka-yoke/scripts/detect_hazards.py`.

- The `id` must match a catalog entry. A detector hit with no catalog entry has nowhere to send
  the reader.
- **Bias toward precision over recall.** A noisy rule trains people to ignore the whole tool,
  which costs more than the hazards it finds. If a rule cannot be written precisely, leave it
  to the lens questions in the skills. An unwritten rule is better than a rule everyone skips.
- Use `negate` for the common legitimate case rather than widening the pattern.
- Severity: `high` = irreversible, silent, or security-relevant. `medium` = wrong behavior
  that surfaces. `low` = worth a look.
- Add fixture cases both ways: a line that must match, and a near-miss that must not.

## Adding a skill

Only if it is a genuinely distinct discipline with its own failure modes and devices. Each
skill widens the triggering surface, and skills competing for the same phrases make every one
of them less reliable to trigger. Prefer a section in an existing skill.

If you do add one: register it nowhere (skills are discovered automatically), but **do** add a
row to the router's dispatch table in `plugins/poka-yoke/skills/poka-yoke/SKILL.md` and to
the README, or nobody will find it.

## Writing style

The skills explain *why* rather than commanding. This is deliberate. A model that understands
the reasoning generalizes to cases the skill never anticipated, while one following rules
applies them where they do not fit. If you find yourself writing ALWAYS or NEVER in capitals,
reframe: say what goes wrong and let the reason carry the weight.

## Validating

```bash
claude plugin validate . --strict
claude plugin validate plugins/poka-yoke --strict
python3 tests/test_detector.py
python3 tests/test_portability.py
python3 tests/test_skill_listing.py
python3 scripts/sync_platform_manifests.py --check
python3 scripts/check_action_pins.py --offline
python3 scripts/check_cited_rules.py
python3 scripts/trigger_eval.py --min-rank1 100
python3 plugins/poka-yoke/scripts/cli.py detect --paths benchmarks/fixtures
python3 plugins/poka-yoke/scripts/cli.py registry --check --write docs/poka-yoke/registry.md
```

CI runs all of these, plus checks that need tooling this list does not assume: actionlint and
`pre-commit validate-config` over the shipped device templates, `check_cited_rules.py` with
`--require`, so an absent linter fails instead of skipping, and an end-to-end install of the
plugin. A green local run is necessary, not sufficient.

If the registry check fails you added a `poka-yoke:` marker comment. Regenerate it with
`registry --write` and commit the result. If the manifest check fails you edited a generated
manifest by hand; edit `plugins/poka-yoke/.claude-plugin/plugin.json` instead and re-run the
sync script. `check_cited_rules.py` skips any linter you do not have installed and says which;
CI has them all, so a rule it skipped for you is still checked before merge.
