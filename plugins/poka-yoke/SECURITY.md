# Security

This plugin ships three Python scripts and a set of markdown skills. Nothing runs on
install, and nothing here reaches the network.

- `scripts/detect_hazards.py` — static scanner. Reads files, writes nothing, standard
  library only. Runs when a skill or a person invokes it.
- `scripts/cli.py` — dispatcher for the scanner.
- `scripts/device_registry.py` — regenerates a documentation table. Developer and CI use.

`assets/devices/` holds templates you choose to copy into your own repository. They are not
installed or registered by the plugin manifest. Read one before you apply it: a `PreToolUse`
hook runs with your agent's permissions.

To report a vulnerability, see the policy in the repository root:
<https://github.com/rainmanjam/poka-yoke/blob/main/SECURITY.md>
