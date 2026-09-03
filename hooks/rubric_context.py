#!/usr/bin/env python3
"""UserPromptSubmit hook: put the verification questions in front of every turn.

A rule in a file read at session start is buried under a hundred thousand
tokens by the time the mistake happens, so the questions arrive on every
prompt instead.

Never blocks, never errors out loud. Any unexpected condition still emits
the core block, because that block depends on nothing and silence here
would be the one turn without it.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rubric import config as rubric_config  # noqa: E402
from rubric import context as rubric_context  # noqa: E402


def project_dir(payload):
    """Where this turn is happening.

    `cwd` is observed in the Stop payload; it has NOT been observed in the
    UserPromptSubmit one, so two fallbacks follow it. All three failing is
    survivable: an unconfigured project still gets the core block.
    """
    for candidate in (payload.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")):
        if candidate and os.path.isdir(candidate):
            return candidate
    return os.getcwd()


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except ValueError:
        payload = {}

    prompt = payload.get("prompt") or ""
    try:
        loaded, _ = rubric_config.load(project_dir(payload))
    except Exception:  # noqa: BLE001
        loaded = dict(rubric_config.DEFAULTS)

    text = rubric_context.build(loaded, prompt)
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - never break a session over this
        sys.exit(0)
