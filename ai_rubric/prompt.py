"""The fixed judge instructions, prompt assembly, and the brief neutrality lint."""

import re

JUDGE_INSTRUCTIONS = """\
You are an independent judge reviewing a proposal. You do not know who wrote it,
and you have no stake in it. Argue on the merits.

Rules:
- Read the workspace yourself. The files named in the brief are a starting point,
  not a limit; open whatever else bears on the question.
- Do not edit, create or delete anything. This is a read-only review.
- Use your file-reading and search tools rather than shell commands. Only these
  read-only commands may be allowed: ls, cat, head, tail, wc, grep, stat, du, pwd.
  Do not run git or any other command; in some judges a refused command ends the
  run with no answer.
- Do not invent facts. Cite file paths (with lines where useful) or sources for
  every claim that matters. If you could not check something, say so.

Answer in markdown with exactly these headings, in this order:

## Case for
The strongest honest case for the proposal as written, with evidence.

## Case against
The strongest honest case against it, with evidence.

## Verdict
One of: keep / change / drop. Then what you would do instead, if anything, and
your confidence (low / medium / high) with the reason.

## Missing
What the proposal overlooks: risks, alternatives, constraints, evidence.

## Evidence
The files, lines and sources your judgment rests on.

## Not checked
What you could not verify, and why.
"""


def build_prompt(brief: str, roots: list[str]) -> str:
    folders = "\n".join(f"- {r}" for r in roots)
    return (f"{JUDGE_INSTRUCTIONS}\n"
            f"Workspace folders you may read:\n{folders}\n\n"
            f"# Brief\n\n{brief}")


_LEAK_PATTERNS = [
    r"\b(claude|codex|antigravity|gemini|gpt|opus|chatgpt)\b",
    r"\bI (feel|think|believe|suspect|doubt|prefer|like|hate)\b",
    r"\b(my|our) (proposal|plan|idea|answer|design)\b",
    r"\buser (thinks|feels|prefers|wants to drop|doubts)\b",
    r"\b(you|I) (wrote|proposed|suggested)\b",
]
_LEAK_RE = [re.compile(p, re.IGNORECASE) for p in _LEAK_PATTERNS]


def lint_brief(brief: str) -> list[str]:
    """Phrases that could reveal who wrote the proposal or which way anyone leans."""
    hits: list[str] = []
    for rx in _LEAK_RE:
        for m in rx.finditer(brief):
            if m.group(0) not in hits:
                hits.append(m.group(0))
    return hits
