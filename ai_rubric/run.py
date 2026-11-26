"""Run both judges in parallel and save the consultation."""

import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .commands import build_command
from .auth import authentication_error, usage_limit_error
from .config import Config
from .discover import find_cli
from .judges import Judge, judges_for, stand_ins_for
from .prompt import build_prompt
from . import __version__, recovery


@dataclass
class Verdict:
    judge: str
    model: str
    ok: bool
    text: str
    error: str | None
    seconds: float
    error_kind: str | None = None


def _slug(brief: str) -> str:
    first = next((ln.strip() for ln in brief.splitlines() if ln.strip()), "consult")
    words = " ".join(first.split()[:6]).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", words).strip("-")[:40].strip("-")
    return slug or "consult"


def make_run_dir(save_root: str, brief: str, now: datetime) -> Path:
    base = Path(save_root).expanduser() / f"{now:%Y%m%d-%H%M%S}-{_slug(brief)}"
    n = 1
    while True:  # create directly: a separate exists() check races with another consult
        path = base if n == 1 else base.with_name(f"{base.name}-{n}")
        try:
            path.mkdir(parents=True, mode=0o700)  # briefs and verdicts are private
            return path
        except FileExistsError:
            n += 1


def _roots(cwd: str, add_dirs: list[str], extra_dirs: list[str]) -> list[str]:
    roots: list[str] = []
    for d in [cwd, *add_dirs, *extra_dirs]:
        p = os.path.abspath(os.path.expanduser(d))
        if p not in roots:
            roots.append(p)
    return roots


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _kill_group(proc: subprocess.Popen) -> None:
    """Stop the judge and every process it started."""
    for sig, wait in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


# Judges run in their own sessions, so Ctrl-C never reaches them; _execute stops these.
_RUNNING: set[subprocess.Popen] = set()
_STOP = threading.Event()  # set on interrupt: nothing new may start


def _kill_now(proc: subprocess.Popen) -> None:
    """Judges are read-only reviewers: on cancel there is nothing to clean up, so no grace period."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_cli(argv: list[str], cwd: str, timeout: int) -> tuple[int, str, str]:
    """Run a judge in its own process group; on timeout kill the whole group."""
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    _RUNNING.add(proc)
    if _STOP.is_set():  # cancelled while this judge was starting; the sweep may have missed it
        _kill_now(proc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        proc.stdout.close()
        proc.stderr.close()
        raise
    finally:
        _RUNNING.discard(proc)
    decode = lambda b: b.decode("utf-8", errors="replace")  # noqa: E731
    return proc.returncode, decode(out), decode(err)


def _run_one(judge: Judge, config: Config, prompt: str, cwd: str,
             add_dirs: list[str], run_dir: Path, log: list[str]) -> Verdict:
    start = time.monotonic()

    def done(ok: bool, text: str = "", error: str | None = None,
             error_kind: str | None = None) -> Verdict:
        secs = round(time.monotonic() - start, 1)
        log.append(f"{judge.name}: ok={ok} seconds={secs} error={error}")
        return Verdict(judge.name, judge.model, ok, text, error, secs, error_kind)

    try:
        cli = find_cli(judge.cli or judge.name, config)
        if cli is None:
            return done(False, error=f"{judge.name} CLI not found")
        out_file = run_dir / f".{judge.name}-last-message.md"
        out_file.unlink(missing_ok=True)
        argv = build_command(judge, cli, prompt, cwd, add_dirs, str(out_file))
        log.append(f"{judge.name}: argv={[a if a != prompt else '<prompt>' for a in argv]}")
        try:
            code, stdout, stderr = _run_cli(argv, cwd, config.timeout)
        except subprocess.TimeoutExpired:
            return done(False, error=f"timed out after {config.timeout}s")
        if code != 0:
            kind = ("authentication_required" if authentication_error(judge.name, stdout, stderr)
                    else "usage_limit" if usage_limit_error(judge.name, stdout, stderr) else None)
            message = "\n".join(part for part in (stdout, stderr) if part)
            return done(False, error=f"exit {code}: {_tail(message)}", error_kind=kind)
        if out_file.is_file():
            text = out_file.read_bytes().decode("utf-8", errors="replace")
            out_file.unlink()
        else:
            text = stdout
        if not text.strip():
            reason = _tail(stderr, 5)
            return done(False, error=f"empty verdict: {reason}" if reason else "empty verdict")
        return done(True, text=text)
    except Exception as exc:  # one judge's failure must never lose the other's verdict
        return done(False, error=f"{type(exc).__name__}: {exc}")


def _run_slot(judge: Judge, config: Config, prompt: str, cwd: str,
              add_dirs: list[str], run_dir: Path, log: list[str],
              claim: Callable[[], Judge | None]) -> Verdict:
    verdict = _run_one(judge, config, prompt, cwd, add_dirs, run_dir, log)
    if verdict.error_kind != "usage_limit" or _STOP.is_set():
        return verdict
    stand_in = claim()
    if stand_in is None:
        log.append(f"{judge.name}: usage limit reached; no stand-in left")
        return verdict
    log.append(f"{judge.name}: usage limit reached; {stand_in.name} stands in")
    return _run_one(stand_in, config, prompt, cwd, add_dirs, run_dir, log)


def _claimer(stand_ins: list[Judge]) -> Callable[[], Judge | None]:
    """Hand each stand-in to at most one slot, first come first served."""
    lock = threading.Lock()

    def claim() -> Judge | None:
        with lock:
            return stand_ins.pop(0) if stand_ins else None
    return claim


def _pre_run(config: Config) -> None:
    if config.pre_run:
        try:
            pre = subprocess.run(config.pre_run, capture_output=True, text=True)
        except OSError as exc:
            raise RuntimeError(f"pre_run command {config.pre_run} could not start: {exc}") from exc
        if pre.returncode != 0:
            raise RuntimeError(f"pre_run command {config.pre_run} failed "
                               f"(exit {pre.returncode}): {_tail(pre.stderr or pre.stdout)}")


def _export_verdict(run_dir: Path, verdict: Verdict) -> None:
    path = run_dir / f"{verdict.judge}.md"
    text = verdict.text if verdict.ok else f"FAILED: {verdict.error}\n"
    if not path.exists() or path.read_bytes() != text.encode("utf-8"):
        recovery.write_text(path, text)


def _drop_stale_exports(run_dir: Path, judges: list[Judge], state: dict) -> None:
    """A stand-in's verdict replaces its slot's FAILED file (and the reverse on a later retry)."""
    held = {record["judge"] for record in state["verdicts"]}
    for name in {j.name for j in judges + stand_ins_for(state["host"])}:
        if name not in held:
            (run_dir / f"{name}.md").unlink(missing_ok=True)


def _execute(run_dir: Path, state: dict, config: Config) -> list[Verdict]:
    judges = judges_for(state["host"])
    verdicts = [Verdict(**record) for record in state["verdicts"]]
    # Repair exports after a prior interruption without invoking successful judges.
    for verdict in verdicts:
        if verdict.ok:
            _export_verdict(run_dir, verdict)
    pending = [(i, judge) for i, judge in enumerate(judges) if not verdicts[i].ok]
    if not pending:
        return verdicts
    kept = {verdicts[i].judge for i in range(len(judges)) if verdicts[i].ok}
    claim = _claimer([s for s in stand_ins_for(state["host"]) if s.name not in kept])
    prompt = (run_dir / "prompt.md").read_bytes().decode("utf-8")
    log_path = run_dir / "run.log"
    log = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    log.append(f"attempt: judges={[j.name for _, j in pending]} time={datetime.now().isoformat()}")
    recovery.save_run(run_dir, state)
    _STOP.clear()
    with ThreadPoolExecutor(max_workers=len(pending)) as pool:
        try:
            futures = {pool.submit(_run_slot, judge, config, prompt, state["cwd"],
                                   state["extra_dirs"], run_dir, log, claim): i for i, judge in pending}
            for future in as_completed(futures):
                i = futures[future]
                v = verdicts[i] = future.result()
                state["verdicts"][i] = asdict(v)
                # Commit the result before exporting it; resume must never rerun a saved success.
                recovery.save_run(run_dir, state)
                _export_verdict(run_dir, v)
                _drop_stale_exports(run_dir, judges, state)
                log_path.write_text("\n".join(log) + "\n", encoding="utf-8")
        except KeyboardInterrupt:
            _STOP.set()
            for proc in list(_RUNNING):
                _kill_now(proc)
            raise
    return verdicts


def run_consult(host: str, brief: str, cwd: str, add_dirs: list[str],
                config: Config) -> tuple[Path, list[Verdict]]:
    judges = judges_for(host)
    _pre_run(config)
    cwd = os.path.abspath(os.path.expanduser(cwd))
    roots = _roots(cwd, add_dirs, config.extra_dirs)
    extra = [r for r in roots if r != cwd]
    prompt = build_prompt(brief, roots)
    run_dir = make_run_dir(config.save_root, brief, datetime.now())
    with recovery.run_lock(run_dir):
        (run_dir / "brief.md").write_text(brief, encoding="utf-8")
        (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
        (run_dir / "run.log").write_text(
            f"host={host} cwd={cwd} roots={roots} timeout={config.timeout}\n", encoding="utf-8")
        state = {"version": 1, "tool_version": __version__, "host": host, "cwd": cwd, "extra_dirs": extra,
                 "started_at": time.time(), "verdicts": [
                     asdict(Verdict(j.name, j.model, False, "", "not completed", 0.0)) for j in judges]}
        try:
            return run_dir, _execute(run_dir, state, config)
        except KeyboardInterrupt as exc:
            exc.run_dir = run_dir  # so the CLI can name the folder to resume
            raise
