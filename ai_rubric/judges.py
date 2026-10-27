"""The three judges and which two judge each host. Pinned on purpose."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Judge:
    name: str
    model: str
    effort: str | None


JUDGES: dict[str, Judge] = {
    "claude": Judge("claude", "claude-opus-5-5", "medium"),
    "codex": Judge("codex", "gpt-6-astra", "medium"),
    "agy": Judge("agy", "gemini-4-argon-high", None),  # effort is part of the model id
}

HOSTS = ("claude", "codex")


def judges_for(host: str) -> list[Judge]:
    """The two judges for a host: the other host, then Antigravity."""
    if host not in HOSTS:
        raise ValueError(f"unknown host {host!r}; expected one of {', '.join(HOSTS)}")
    other = "codex" if host == "claude" else "claude"
    return [JUDGES[other], JUDGES["agy"]]
