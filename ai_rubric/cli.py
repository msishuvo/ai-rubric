"""consult: get blind, two-sided verdicts from the other two judges."""

import argparse
import os
import shlex
import signal
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .judges import HOSTS
from .prompt import lint_brief
from .run import run_consult
from .recovery import resume_consult
from .discover import find_cli

LINT_MESSAGE = ("Brief may reveal authorship or leaning: {hits}. Rewrite it neutrally, "
                "or pass --allow-flagged if these words are part of the subject itself.")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="consult", description=__doc__)
    p.add_argument("--version", action="version", version=f"consult {__version__}")
    p.add_argument("--from", dest="host", choices=HOSTS,
                   help="the tool asking: claude (Claude Code) or codex")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--brief", help="file holding the neutral brief")
    source.add_argument("--resume", metavar="DIR", help="retry only failed judges from a saved run")
    p.add_argument("--login", action="store_true",
                   help="with --resume, sign in to Claude interactively and then retry")
    p.add_argument("--add-dir", action="append", default=[], metavar="DIR",
                   help="extra workspace folder judges may read (repeatable)")
    p.add_argument("--allow-flagged", action="store_true",
                   help="run even if the brief mentions tool names or leanings")
    p.add_argument("--config", help="config file (default ~/.config/ai-rubric/config.toml)")
    return p


def _resume_command(run_dir, config_arg: str | None) -> list[str]:
    command = ["consult", "--resume", str(run_dir)]
    if config_arg:
        command.extend(["--config", str(Path(config_arg).absolute())])
    return command


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    # A host stopping a background run sends SIGTERM (or SIGHUP): take the Ctrl-C path so judges stop.
    for sig in (signal.SIGTERM, signal.SIGHUP):
        if signal.getsignal(sig) != signal.SIG_IGN:  # keep a deliberate `nohup`
            signal.signal(sig, signal.default_int_handler)
    if args.resume and (args.host or args.add_dir or args.allow_flagged):
        print("consult: --resume uses saved context; omit --from, --add-dir, and --allow-flagged", file=sys.stderr)
        return 2
    if not args.resume and (not args.host or args.login):
        print("consult: fresh runs require --from; --login requires --resume", file=sys.stderr)
        return 2
    try:
        config = load_config(Path(args.config) if args.config else None)
    except (ValueError, OSError) as exc:
        print(f"consult: bad config: {exc}", file=sys.stderr)
        return 2
    if not args.resume:
        try:
            brief = Path(args.brief).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"consult: cannot read brief: {exc}", file=sys.stderr)
            return 2
        missing = [d for d in args.add_dir if not os.path.isdir(os.path.expanduser(d))]
        if missing:
            print(f"consult: --add-dir folder not found: {', '.join(missing)}", file=sys.stderr)
            return 2
        hits = lint_brief(brief)
        if hits and not args.allow_flagged:
            print(LINT_MESSAGE.format(hits=", ".join(hits)), file=sys.stderr)
            return 3
    try:
        if args.resume:
            run_dir, verdicts = resume_consult(Path(args.resume), config, login=args.login)
        else:
            run_dir, verdicts = run_consult(args.host, brief, os.getcwd(), args.add_dir, config)
    except (RuntimeError, OSError) as exc:
        print(f"consult: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt as exc:
        run_dir = getattr(exc, "run_dir", None) or args.resume  # fresh runs attach it; none before a folder exists
        print("consult: cancelled; judges stopped."
              + (f" Retry the unfinished judges: {shlex.join(_resume_command(run_dir, args.config))}"
                 if run_dir else ""), file=sys.stderr)
        return 130
    for v in verdicts:
        status = "ok" if v.ok else "FAILED"
        print(f"=== {v.judge} ({v.model}) — {status} ===")
        print(v.text.rstrip() if v.ok else v.error)
        print()
    if any(v.judge == "neon" for v in verdicts):
        print("Note: the other host's model hit its usage limit; Gemini Neon was called in its place.\n")
    successes = sum(v.ok for v in verdicts)
    if 0 < successes < len(verdicts):
        print(f"PARTIAL: {successes} of {len(verdicts)} judges completed.\n")
    if any(v.error_kind == "authentication_required" for v in verdicts):
        print("Claude needs you to sign in again. Your completed verdicts are saved.")
        login_command = [find_cli("claude", config) or "claude", "auth", "login", "--claudeai"]
        resume_command = _resume_command(run_dir, args.config)
        print(f"In an interactive terminal: {shlex.join(resume_command + ['--login'])}")
        print(f"Or sign in manually: {shlex.join(login_command)}")
        print(f"Then retry failed judges: {shlex.join(resume_command)}\n")
    elif any(not v.ok for v in verdicts):
        resume_command = _resume_command(run_dir, args.config)
        print(f"Retry failed judges: {shlex.join(resume_command)}\n")
    print(f"Saved: {run_dir}")
    return 0 if any(v.ok for v in verdicts) else 1
