"""Load and merge Rubric configuration.

Resolution order, later wins:

  1. DEFAULTS
  2. presets/<dialect>.json
  3. ~/.claude/rubric.json        (per device: mainly `who` and `cannot_check`)
  4. <project>/.claude/rubric.json

Objects deep-merge. Arrays replace wholesale, unless the overlay key
carries a trailing "+", in which case it appends to the inherited value.
That form exists because the common edit is "the preset is right, plus one
more command", and forcing a full retype of the preset's list is how a
rule silently disappears during an unrelated edit.

Nothing here raises. A configuration file that cannot be read is treated
as absent, because the alternative is a hook that crashes a session over a
stray comma.
"""

import json
import os

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "dialect": None,
    "who": None,
    "cannot_check": [],
    "work_files": [],
    "evidence": {"commands": [], "tools": [], "never_started": []},
    "claims": [],
    "disclaimers": [],
    "gate": {"enabled": False, "requires_work_change": True},
    "cost_table": [],
    "situations": [],
    "invariants": [],
}


def read_json(path):
    """The parsed object at `path`, or None. Never raises."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def deep_merge(base, overlay):
    """`overlay` applied over `base`. Objects merge, arrays replace.

    A key ending in "+" appends to the inherited array instead of
    replacing it, and the "+" is stripped from the resulting key. A
    non-list overlay value is wrapped as a single-element list rather than
    iterated, so a user writing {"claims+": "looks good"} in place of the
    correct {"claims+": ["looks good"]} gets one appended string, not one
    appended character per letter.
    """
    out = dict(base)
    for key, value in (overlay or {}).items():
        if key.endswith("+"):
            name = key[:-1]
            inherited = out.get(name)
            if value is None:
                addition = []
            elif isinstance(value, list):
                addition = value
            else:
                # A scalar overlay value, most likely a string a user wrote
                # in place of a one-item list ("claims+": "looks good"). It
                # is wrapped rather than iterated, because iterating a
                # string appends it one character at a time.
                addition = [value]
            out[name] = list(inherited or []) + list(addition)
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def read_preset(dialect, plugin_root=None):
    """The named dialect preset, or an empty dict if there is no such file."""
    if not dialect or not isinstance(dialect, str):
        return {}
    if not dialect.replace("-", "").replace("_", "").isalnum():
        # A dialect name is a filename. Refuse anything that could traverse.
        return {}
    root = plugin_root or PLUGIN_ROOT
    return read_json(os.path.join(root, "presets", dialect + ".json")) or {}


def load(project_dir, home_dir=None, plugin_root=None):
    """`(config, project_configured)` for a project directory.

    `project_configured` is False when the project has no rubric.json. The
    gate keys on that bool rather than on the config's contents: a
    device-level file naming only `who` is not enough knowledge to judge
    what evidence means in a repository the kit has never been told about.
    """
    home_dir = home_dir if home_dir is not None else os.path.expanduser("~")

    project_cfg = read_json(os.path.join(project_dir or "", ".claude", "rubric.json"))
    user_cfg = read_json(os.path.join(home_dir, ".claude", "rubric.json"))

    merged = dict(DEFAULTS)
    merged["evidence"] = dict(DEFAULTS["evidence"])
    merged["gate"] = dict(DEFAULTS["gate"])

    dialect = (project_cfg or {}).get("dialect") or (user_cfg or {}).get("dialect")
    if dialect:
        merged = deep_merge(merged, read_preset(dialect, plugin_root))
    if user_cfg:
        merged = deep_merge(merged, user_cfg)
    if project_cfg:
        merged = deep_merge(merged, project_cfg)

    configured = project_cfg is not None
    # Only read explicit if gate is actually a dict in project config
    project_gate = (project_cfg or {}).get("gate")
    explicit = project_gate.get("enabled") if isinstance(project_gate, dict) else None

    # If gate is malformed (not a dict) after merges, reset to default
    if not isinstance(merged.get("gate"), dict):
        merged["gate"] = dict(DEFAULTS["gate"])

    merged["gate"]["enabled"] = configured if explicit is None else bool(explicit)

    return merged, configured
