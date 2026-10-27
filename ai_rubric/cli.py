"""consult: get blind, two-sided verdicts from the other two judges."""

import argparse
import os
import sys
from pathlib import Path

from .config import load_config
from .judges import HOSTS
from .prompt import lint_brief
from .run import run_consult

LINT_MESSAGE = ("Brief may reveal authorship or leaning: {hits}. Rewrite it neutrally, "
                "or pass --allow-flagged if these words are part of the subject itself.")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="consult", description=__doc__)
    p.add_argument("--from", dest="host", required=True, choices=HOSTS,
                   help="the tool asking: claude (Claude Code) or codex")
    p.add_argument("--brief", required=True, help="file holding the neutral brief")
    p.add_argument("--add-dir", action="append", default=[], metavar="DIR",
                   help="extra workspace folder judges may read (repeatable)")
    p.add_argument("--allow-flagged", action="store_true",
                   help="run even if the brief mentions tool names or leanings")
    p.add_argument("--config", help="config file (default ~/.config/ai-rubric/config.toml)")
    return p


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        brief = Path(args.brief).read_text()
    except OSError as exc:
        print(f"consult: cannot read brief: {exc}", file=sys.stderr)
        return 2
    try:
        config = load_config(Path(args.config) if args.config else None)
    except (ValueError, OSError) as exc:
        print(f"consult: bad config: {exc}", file=sys.stderr)
        return 2
    hits = lint_brief(brief)
    if hits and not args.allow_flagged:
        print(LINT_MESSAGE.format(hits=", ".join(hits)), file=sys.stderr)
        return 3
    try:
        run_dir, verdicts = run_consult(args.host, brief, os.getcwd(), args.add_dir, config)
    except RuntimeError as exc:
        print(f"consult: {exc}", file=sys.stderr)
        return 2
    for v in verdicts:
        status = "ok" if v.ok else "FAILED"
        print(f"=== {v.judge} ({v.model}) — {status} ===")
        print(v.text.rstrip() if v.ok else v.error)
        print()
    print(f"Saved: {run_dir}")
    return 0 if any(v.ok for v in verdicts) else 1
