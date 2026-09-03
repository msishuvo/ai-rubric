"""Decide whether a turn may end.

Blocks when all of these hold, and only then:

  1. the gate is enabled (which means the project has a rubric.json)
  2. some assistant TEXT this turn makes a completion claim
  3. that text carries no disclaimer
  4. if the dialect requires it, a work file actually changed
  5. nothing that counts as evidence ran, or something did and its own
     output says it never started

The conjunction is deliberately tight. Discussion, refactors reported
honestly, and answering a question all pass untouched.

Nothing here does I/O. `evaluate` takes records and returns a verdict; the
hook shell is what reads stdin and prints.
"""

import re

from rubric import globs, transcript

# A shell command that WRITES, as opposed to one that merely mentions a
# path. `grep -n foo src/a.py` mentions; `cat > src/a.py` writes. Auto mode
# edits through Bash, so missing this would quietly retire the gate.
WRITE_HINTS = [
    r">\s*\S+",
    r"\bsed\s+-i\b",
    r"\btee\b",
    r"\bpatch\b",
    r"\bdd\b",
    r"\bmv\s",
    r"\bcp\s",
]
WRITE_HINT_RE = re.compile("|".join(WRITE_HINTS))
PATH_TOKEN_RE = re.compile(r"[\w./\-]+")

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


class Verdict(object):
    """A decision to block, and the sentence explaining it."""

    def __init__(self, reason, claims):
        self.reason = reason
        self.claims = claims


class Signals(object):
    """What this turn actually contained."""

    def __init__(self, said, claims, work_changed, has_evidence):
        self.said = said
        self.claims = claims
        self.work_changed = work_changed
        self.has_evidence = has_evidence


def _search_any(patterns, text):
    for pattern in patterns or []:
        try:
            if re.search(pattern, text or "", re.IGNORECASE):
                return True
        except (re.error, TypeError):
            continue
    return False


def _found(patterns, text):
    out = []
    for pattern in patterns or []:
        try:
            out.extend(m.group(0) for m in re.finditer(pattern, text or "", re.IGNORECASE))
        except (re.error, TypeError):
            continue
    return sorted(set(out))


def work_changed(config, turn):
    """True when a path matching `work_files` was written this turn."""
    patterns = config.get("work_files") or []
    if not patterns:
        return False
    for name, tool_input, _ in transcript.tool_uses(turn):
        if name in EDIT_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            if globs.matches_any(path, patterns):
                return True
        elif name == "Bash":
            command = tool_input.get("command") or ""
            if not WRITE_HINT_RE.search(command):
                continue
            for token in PATH_TOKEN_RE.findall(command):
                if globs.matches_any(token, patterns):
                    return True
    return False


def has_evidence(config, turn):
    """True when something ran that actually exercised the project.

    A call whose own output matches `never_started` does not count. That
    rule exists because a build tool can print an error, do nothing, and
    still exit clean, so nothing downstream can tell it apart from a real
    run unless the output is read.
    """
    evidence = config.get("evidence") or {}
    commands = evidence.get("commands") or []
    tools = evidence.get("tools") or []
    never_started = evidence.get("never_started") or []
    results = transcript.tool_results(turn)

    for name, tool_input, use_id in transcript.tool_uses(turn):
        counted = False
        if name == "Bash":
            counted = _search_any(commands, tool_input.get("command") or "")
        else:
            counted = any(name == t or name.startswith(t) for t in tools)
        if not counted:
            continue
        if _search_any(never_started, results.get(use_id, "")):
            continue
        return True
    return False


def signals(config, turn):
    said = transcript.assistant_text(turn)
    return Signals(
        said=said,
        claims=_found(config.get("claims"), said),
        work_changed=work_changed(config, turn),
        has_evidence=has_evidence(config, turn),
    )


def _checks_available(config):
    rows = config.get("cost_table") or []
    parts = []
    for row in rows[:3]:
        check = (row or {}).get("check")
        if not check:
            continue
        cost = (row or {}).get("cost")
        parts.append("%s (%s)" % (check, cost) if cost else check)
    return parts


def _reason(config, found_claims):
    quoted = " / ".join('"%s"' % c for c in found_claims[:3])
    checks = _checks_available(config)
    if checks:
        suffix = ("Run one of these first: %s. " % "; ".join(checks))
    else:
        suffix = ("No check is configured for this project, so either run "
                  "whatever would actually settle it, or say so. ")
    return (
        "This turn told the user %s, but nothing ran that would show it. "
        "%s"
        'Otherwise write "I have not checked this" in the reply, in the '
        "sentence making the claim, and stop." % (quoted, suffix)
    )


def decide(config, computed):
    """A Verdict to block, or None to allow. Pure."""
    if not (config.get("gate") or {}).get("enabled"):
        return None
    if not computed.claims:
        return None
    if _search_any(config.get("disclaimers"), computed.said):
        return None
    if (config.get("gate") or {}).get("requires_work_change", True) and not computed.work_changed:
        return None
    if computed.has_evidence:
        return None
    return Verdict(_reason(config, computed.claims), computed.claims)


def evaluate(config, records, stop_hook_active=False):
    if stop_hook_active:
        return None
    turn = transcript.current_turn(records)
    return decide(config, signals(config, turn))
