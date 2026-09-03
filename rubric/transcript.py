"""Read one turn out of a Claude Code transcript.

This is the only module that knows the JSONL record shape. Everything
downstream takes primitives, so a change to the host's transcript format
is a change to exactly one file.
"""

import json

# Injected context, slash-command echoes and hook output all arrive as user
# records. None of them is the human speaking, so none of them starts a turn.
NON_PROMPT_PREFIXES = (
    "<system-reminder", "<command-", "<local-command", "<bash-", "<user-prompt",
)


def blocks(record):
    """The content blocks of a record, normalised to a list of dicts."""
    message = (record or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def is_human_prompt(record):
    """True for a record that is the person typing, not a tool result."""
    if (record or {}).get("type") != "user" or record.get("isMeta"):
        return False
    for block in blocks(record):
        if block.get("type") != "text":
            continue
        body = (block.get("text") or "").strip()
        if body and not body.startswith(NON_PROMPT_PREFIXES):
            return True
    return False


def current_turn(records):
    """Records since the last human prompt.

    A subagent's lines land in the same transcript with `isSidechain` set.
    Its build is not this session's evidence and its prose is not this
    session's claim, so they are dropped before anything else looks.
    """
    own = [r for r in (records or []) if not (r or {}).get("isSidechain")]
    start = 0
    for index, record in enumerate(own):
        if is_human_prompt(record):
            start = index + 1
    return own[start:]


def assistant_text(turn):
    """Everything the user was actually told this turn.

    Thinking blocks are excluded on purpose: a claim the user never reads
    cannot mislead them, and gating on private reasoning would fire the
    hook on deliberating about whether something is fixed.
    """
    out = []
    for record in turn or []:
        if (record or {}).get("type") != "assistant":
            continue
        for block in blocks(record):
            if block.get("type") == "text":
                out.append(block.get("text") or "")
    return "\n".join(out)


def tool_uses(turn):
    """`(name, input, tool_use_id)` for every tool call this turn."""
    for record in turn or []:
        for block in blocks(record):
            if block.get("type") == "tool_use":
                yield (block.get("name") or "",
                       block.get("input") or {},
                       block.get("id") or "")


def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text") or "")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def tool_results(turn):
    """`tool_use_id` -> result text, for results that name their call.

    An unattributed result is skipped rather than guessed at: pairing it to
    the wrong call would let one command's failure disqualify another's
    success, which is a worse error than missing a failure.
    """
    out = {}
    for record in turn or []:
        for block in blocks(record):
            if block.get("type") != "tool_result":
                continue
            key = block.get("tool_use_id")
            if not key:
                continue
            out[key] = out.get(key, "") + _result_text(block.get("content"))
    return out


def read(path):
    """Every parseable record in a transcript file. Never raises."""
    records = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return records
