#!/usr/bin/env python3
"""Stop hook: refuse to end a turn that claims work is done with nothing behind it.

Blocking a Stop makes the model continue, which produces another Stop. Two
independent things prevent a loop, because relying on one of them means
trusting a payload field that may not always arrive:

  * `stop_hook_active` in the stdin payload, when the host sends it;
  * a per-session marker file recording that this session was already
    blocked. One block per session is the whole intent anyway. The point
    is to interrupt the reflex once, not to argue.

Every unexpected condition exits 0 and allows the stop. A gate that breaks
a session is worse than no gate; it gets removed within a day and takes its
protection with it.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rubric import config as rubric_config  # noqa: E402
from rubric import gate as rubric_gate  # noqa: E402
from rubric import transcript as rubric_transcript  # noqa: E402


def state_dir(payload):
    """Somewhere writable for the per-session marker.

    `scratchpad_dir` was observed in the live Stop payload. The plugin's
    own directory is deliberately not used: it lives in the plugins cache
    and is replaced wholesale on update.
    """
    base = payload.get("scratchpad_dir") or tempfile.gettempdir()
    path = os.path.join(base, "rubric-gate")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return None
    return path


def already_blocked(directory, session_id):
    if not directory or not session_id:
        return False
    return os.path.exists(os.path.join(directory, "blocked-%s" % session_id))


def mark_blocked(directory, session_id):
    if not directory or not session_id:
        return
    try:
        open(os.path.join(directory, "blocked-%s" % session_id), "a").close()
    except OSError:
        pass


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0

    transcript_path = payload.get("transcript_path") or ""
    if not transcript_path or not os.path.exists(transcript_path):
        return 0

    directory = state_dir(payload)
    session_id = payload.get("session_id") or ""
    if already_blocked(directory, session_id):
        return 0

    loaded, configured = rubric_config.load(payload.get("cwd") or os.getcwd())
    if not configured:
        return 0

    verdict = rubric_gate.evaluate(
        loaded,
        rubric_transcript.read(transcript_path),
        stop_hook_active=bool(payload.get("stop_hook_active")),
    )
    if verdict is None:
        return 0

    mark_blocked(directory, session_id)
    if verdict.kind == "misconfigured":
        system_message = "Rubric: the gate is misconfigured and cannot fire."
    else:
        system_message = "Rubric: a completion claim with no check behind it."
    print(json.dumps({
        "decision": "block",
        "reason": verdict.reason,
        "systemMessage": system_message,
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001; never break the session over this
        sys.exit(0)
