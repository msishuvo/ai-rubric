"""Insert, replace or remove one marked block in a text file, leaving the rest untouched.

Used by install.sh:  python3 blocks.py upsert|remove|check FILE md|hash [FRAGMENT_FILE]
Reads and writes UTF-8 with newlines untranslated, and matches the file's line endings.
"""

from __future__ import annotations

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
    for nl in ("\r\n", "\n"):
        if text.startswith(nl, j):
            j += len(nl)
            break
    return i, j


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def upsert_block(text: str, body: str, start: str, end: str) -> str:
    nl = _newline(text)
    lines = body.replace("\r\n", "\n").rstrip().split("\n")
    block = nl.join([start, *lines, end]) + nl
    span = _span(text, start, end)
    if span:
        return text[:span[0]] + block + text[span[1]:]
    if not text:
        return block
    sep = nl if text.endswith(nl) else nl + nl
    return text + sep + block


def remove_block(text: str, start: str, end: str) -> str:
    span = _span(text, start, end)
    if not span:
        return text
    before, after = text[:span[0]], text[span[1]:]
    nl = _newline(text)
    if before.endswith(nl + nl):
        before = before[:-len(nl)]  # the blank line upsert added
    return before + after


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main(argv: list[str]) -> int:
    action, file, style = argv[0], Path(argv[1]), argv[2]
    start, end = MARKERS[style]
    text = _read(file) if file.exists() else ""
    if action == "check":
        try:
            _span(text, start, end)
        except ValueError as exc:
            print(f"{file}: {exc}", file=sys.stderr)
            return 1
        return 0
    if action == "upsert":
        body = _read(Path(argv[3]))
        file.parent.mkdir(parents=True, exist_ok=True)
        new = upsert_block(text, body, start, end)
    elif action == "remove":
        if not file.exists():
            return 0
        new = remove_block(text, start, end)
    else:
        raise SystemExit(f"unknown action {action!r}")
    if new != text or not file.exists():
        _write(file, new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
