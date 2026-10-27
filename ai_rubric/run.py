"""Run both judges in parallel and save the consultation."""

import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .commands import build_command
from .config import Config
from .discover import find_cli
from .judges import Judge, judges_for
from .prompt import build_prompt


@dataclass
class Verdict:
    judge: str
    model: str
    ok: bool
    text: str
    error: str | None
    seconds: float


def _slug(brief: str) -> str:
    first = next((ln.strip() for ln in brief.splitlines() if ln.strip()), "consult")
    words = " ".join(first.split()[:6]).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", words).strip("-")[:40].strip("-")
    return slug or "consult"


def make_run_dir(save_root: str, brief: str, now: datetime) -> Path:
    base = Path(save_root).expanduser() / f"{now:%Y%m%d-%H%M%S}-{_slug(brief)}"
    path, n = base, 2
    while path.exists():
        path, n = base.with_name(f"{base.name}-{n}"), n + 1
    path.mkdir(parents=True)
    return path


def _roots(cwd: str, add_dirs: list[str], extra_dirs: list[str]) -> list[str]:
    roots: list[str] = []
    for d in [cwd, *add_dirs, *extra_dirs]:
        p = os.path.abspath(os.path.expanduser(d))
        if p not in roots:
            roots.append(p)
    return roots


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _run_one(judge: Judge, config: Config, prompt: str, cwd: str,
             add_dirs: list[str], run_dir: Path, log: list[str]) -> Verdict:
    start = time.monotonic()

    def done(ok: bool, text: str = "", error: str | None = None) -> Verdict:
        secs = round(time.monotonic() - start, 1)
        log.append(f"{judge.name}: ok={ok} seconds={secs} error={error}")
        return Verdict(judge.name, judge.model, ok, text, error, secs)

    cli = find_cli(judge.name, config)
    if cli is None:
        return done(False, error=f"{judge.name} CLI not found")
    out_file = run_dir / f".{judge.name}-last-message.md"
    argv = build_command(judge, cli, prompt, cwd, add_dirs, str(out_file))
    log.append(f"{judge.name}: argv={[a if a != prompt else '<prompt>' for a in argv]}")
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=config.timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return done(False, error=f"timed out after {config.timeout}s")
    except OSError as exc:
        return done(False, error=f"could not start {cli}: {exc}")
    if proc.returncode != 0:
        return done(False, error=f"exit {proc.returncode}: {_tail(proc.stderr or proc.stdout)}")
    text = out_file.read_text() if out_file.is_file() else proc.stdout
    out_file.unlink(missing_ok=True)
    if not text.strip():
        return done(False, error="empty verdict")
    return done(True, text=text)


def run_consult(host: str, brief: str, cwd: str, add_dirs: list[str],
                config: Config) -> tuple[Path, list[Verdict]]:
    judges = judges_for(host)
    if config.pre_run:
        try:
            pre = subprocess.run(config.pre_run, capture_output=True, text=True)
        except OSError as exc:
            raise RuntimeError(f"pre_run command {config.pre_run} could not start: {exc}") from exc
        if pre.returncode != 0:
            raise RuntimeError(f"pre_run command {config.pre_run} failed "
                               f"(exit {pre.returncode}): {_tail(pre.stderr or pre.stdout)}")
    cwd = os.path.abspath(os.path.expanduser(cwd))
    roots = _roots(cwd, add_dirs, config.extra_dirs)
    extra = [r for r in roots if r != cwd]
    prompt = build_prompt(brief, roots)
    run_dir = make_run_dir(config.save_root, brief, datetime.now())
    (run_dir / "brief.md").write_text(brief)
    (run_dir / "prompt.md").write_text(prompt)
    log: list[str] = [f"host={host} cwd={cwd} roots={roots} timeout={config.timeout}"]
    with ThreadPoolExecutor(max_workers=len(judges)) as pool:
        futures = [pool.submit(_run_one, j, config, prompt, cwd, extra, run_dir, log)
                   for j in judges]
        verdicts = [f.result() for f in futures]
    for v in verdicts:
        (run_dir / f"{v.judge}.md").write_text(v.text if v.ok else f"FAILED: {v.error}\n")
    (run_dir / "run.log").write_text("\n".join(log) + "\n")
    return run_dir, verdicts
