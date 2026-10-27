"""Insert, replace or remove one marked block in a text file, leaving the rest untouched.

Used by install.sh:  python3 blocks.py upsert|remove FILE md|hash [FRAGMENT_FILE]
"""

import sys
from pathlib import Path

MARKERS = {
    "md": ("<!-- ai-rubric start -->", "<!-- ai-rubric end -->"),
    "hash": ("# ai-rubric start", "# ai-rubric end"),
}


def _span(text: str, start: str, end: str) -> tuple[int, int] | None:
    i = text.find(start)
    if i < 0:
        return None
    j = text.find(end, i)
    if j < 0:
        raise ValueError(f"found {start!r} without {end!r}; fix the file by hand")
    j += len(end)
    if text[j:j + 1] == "\n":
        j += 1
    return i, j


def upsert_block(text: str, body: str, start: str, end: str) -> str:
    block = f"{start}\n{body.rstrip()}\n{end}\n"
    span = _span(text, start, end)
    if span:
        return text[:span[0]] + block + text[span[1]:]
    if not text:
        return block
    sep = "\n" if text.endswith("\n") else "\n\n"
    return text + sep + block


def remove_block(text: str, start: str, end: str) -> str:
    span = _span(text, start, end)
    if not span:
        return text
    before, after = text[:span[0]], text[span[1]:]
    if before.endswith("\n\n"):
        before = before[:-1]  # the blank line upsert added
    return before + after


def main(argv: list[str]) -> int:
    action, file, style = argv[0], Path(argv[1]), argv[2]
    start, end = MARKERS[style]
    text = file.read_text() if file.exists() else ""
    if action == "upsert":
        body = Path(argv[3]).read_text()
        file.parent.mkdir(parents=True, exist_ok=True)
        new = upsert_block(text, body, start, end)
    elif action == "remove":
        if not file.exists():
            return 0
        new = remove_block(text, start, end)
    else:
        raise SystemExit(f"unknown action {action!r}")
    if new != text or not file.exists():
        file.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
