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
    "agy": Judge("agy", "gemini-4-carbon-high", None),  # effort is part of the model id
}

# Neon stands in for the other host's model when that model hits its usage limit,
# so a consultation still gets two verdicts.
FALLBACK = Judge("neon", "gemini-4-neon-high", None, cli="agy")

HOSTS = ("claude", "codex", "agy")


def _check(host: str) -> None:
    if host not in HOSTS:
        raise ValueError(f"unknown host {host!r}; expected one of {', '.join(HOSTS)}")


def judges_for(host: str) -> list[Judge]:
    """The two judges for a host: the two models it is not."""
    _check(host)
    if host == "agy":
        return [JUDGES["claude"], JUDGES["codex"]]
    other = "codex" if host == "claude" else "claude"
    return [JUDGES[other], JUDGES["agy"]]


def stand_ins_for(host: str) -> list[Judge]:
    """Who fills a usage-limited slot, in order; each runs at most once per consultation."""
    _check(host)
    return [JUDGES["agy"], FALLBACK] if host == "agy" else [FALLBACK]
