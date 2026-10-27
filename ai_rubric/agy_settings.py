"""Pre-approve strictly read-only shell commands for Antigravity's headless judge runs.

Headless `agy -p` cannot ask for permission, so any unapproved shell command ends the
run with no output. Commands with any write or execute option (find -delete, rg --pre,
tree -o, file -C, sed -i) and all git subcommands are deliberately left out.
Plan mode still blocks writes such as shell redirects.

Used by install.sh:  python3 agy_settings.py add|remove SETTINGS STATE
"""

import json
import sys
from pathlib import Path

READ_ONLY_RULES = [
    "command(ls)", "command(cat)", "command(head)", "command(tail)", "command(wc)",
    "command(grep)", "command(stat)", "command(du)", "command(pwd)",
]
# No git subcommands: a repository's own config (core.fsmonitor, core.pager, ...) can make
# even `git status` run arbitrary programs.


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if text.strip() else {}


def _indent(path: Path) -> int:
    """The file's own indent width (first indented line), else 2."""
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            stripped = line.lstrip(" ")
            if stripped and len(stripped) < len(line):
                return len(line) - len(stripped)
    return 2


def _save(path: Path, data: dict) -> None:
    indent = _indent(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def add_rules(settings: Path, state: Path) -> None:
    data = _load(settings)
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    added = json.loads(state.read_text()) if state.is_file() else []
    for rule in READ_ONLY_RULES:
        if rule not in allow:
            allow.append(rule)
            added.append(rule)
    _save(settings, data)
    _save(state, sorted(set(added)))


def remove_rules(settings: Path, state: Path) -> None:
    try:
        added = set(json.loads(state.read_text()))
    except (OSError, ValueError):
        added = set(READ_ONLY_RULES)  # record lost: remove every rule we could have added
    data = _load(settings)
    perms = data.get("permissions", {})
    if "allow" in perms:
        perms["allow"] = [r for r in perms["allow"] if r not in added]
        if not perms["allow"]:
            del perms["allow"]
    if "permissions" in data and not data["permissions"]:
        del data["permissions"]
    if settings.is_file():
        _save(settings, data)
    state.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    action, settings, state = argv[0], Path(argv[1]), Path(argv[2])
    {"add": add_rules, "remove": remove_rules}[action](settings, state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
