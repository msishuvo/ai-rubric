"""Fake transcript records, in the JSONL shape Claude Code writes.

The records are the whole contract for the gate: it never touches a real
project, a network or a filesystem, so its behaviour is fully determined
by what these builders produce.
"""


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def meta_user(text):
    """A hook injection or slash-command echo. Not the human speaking."""
    return {"type": "user", "isMeta": True,
            "message": {"role": "user", "content": text}}


def assistant(*content):
    return {"type": "assistant",
            "message": {"role": "assistant", "content": list(content)}}


def sidechain_assistant(*content):
    record = assistant(*content)
    record["isSidechain"] = True
    return record


def text(body):
    return {"type": "text", "text": body}


def thinking(body):
    return {"type": "thinking", "thinking": body}


def tool_use(name, tool_input, use_id="t1"):
    return {"type": "tool_use", "name": name, "input": tool_input, "id": use_id}


def tool_result(body, use_id="t1"):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": use_id, "content": body}]}}


def bash(command, use_id="t1"):
    return tool_use("Bash", {"command": command}, use_id)


def edit(path, use_id="t1"):
    return tool_use("Edit", {"file_path": path}, use_id)
