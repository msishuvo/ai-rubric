"""The three judges and which two judge each host. Pinned on purpose."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Judge:
    name: str
    model: str
    effort: str | None
    cli: str = ""  # which CLI runs it, when not the judge's own name


JUDGES: dict[str, Judge] = {
    "claude": Judge("claude", "claude-opus-5-5", "high"),
    "codex": Judge("codex", "gpt-6.2-astra", "high"),
    "agy": Judge("agy", "gemini-4-neon-high", None),  # effort is part of the model id
}

# Stands in for the other host's model when that model hits its usage limit,
# so a consultation still gets two verdicts.
FALLBACK = Judge("argon", "gemini-4-argon-high", None, cli="agy")

HOSTS = ("claude", "codex")


def judges_for(host: str) -> list[Judge]:
    """The two judges for a host: the other host, then Antigravity."""
    if host not in HOSTS:
        raise ValueError(f"unknown host {host!r}; expected one of {', '.join(HOSTS)}")
    other = "codex" if host == "claude" else "claude"
    return [JUDGES[other], JUDGES["agy"]]
