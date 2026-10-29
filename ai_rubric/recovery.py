"""Versioned consultation checkpoints and explicit failed-judge recovery."""

import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Config
from .judges import HOSTS, judges_for

if TYPE_CHECKING:
    from .run import Verdict


def write_text(path: Path, data: str) -> None:
    """Replace one saved artifact atomically so interrupted writes remain readable."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_run(run_dir: Path, state: dict) -> None:
    """The manifest is the authoritative checkpoint; verdict files are exports."""
    write_text(run_dir / "run.json", json.dumps(state, ensure_ascii=False, indent=2,
                                               allow_nan=False) + "\n")


@contextmanager
def run_lock(run_dir: Path):
    """Keep initial runs and explicit resumes from invoking the same judge twice."""
    path = run_dir / ".run.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("Consultation is already running (or was interrupted). "
                           "Remove .run.lock only after confirming it has stopped.") from exc
    os.close(fd)
    try:
        yield
    finally:
        path.unlink()


def load_run(run_dir: Path) -> dict:
    """Validate identities and paths before using any saved execution context."""
    try:
        state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
            raise ValueError("unsupported manifest version")
        if state.get("host") not in HOSTS:
            raise ValueError("invalid host")
        paths = [state["cwd"], *state["extra_dirs"]]
        if not isinstance(state["extra_dirs"], list) or not all(
                isinstance(p, str) and os.path.isabs(p) for p in paths):
            raise ValueError("workspace paths must be absolute")
        started = state["started_at"]
        if type(started) not in (int, float) or not math.isfinite(started) or started <= 0:
            raise ValueError("invalid start time")
        records = state["verdicts"]
        judges = judges_for(state["host"])
        if not isinstance(records, list) or len(records) != len(judges):
            raise ValueError("invalid judge results")
        for record, judge in zip(records, judges):
            if not isinstance(record, dict) or set(record) != {
                    "judge", "model", "ok", "text", "error", "seconds", "error_kind"}:
                raise ValueError("invalid verdict fields")
            if record["judge"] != judge.name or record["model"] != judge.model:
                raise ValueError("saved judge does not match the pinned assignments")
            if (type(record["ok"]) is not bool or not isinstance(record["text"], str)
                    or (record["error"] is not None and not isinstance(record["error"], str))
                    or record["error_kind"] not in (None, "authentication_required")
                    or (record["error_kind"] is not None and judge.name != "claude")
                    or type(record["seconds"]) not in (int, float)
                    or not math.isfinite(record["seconds"]) or record["seconds"] < 0):
                raise ValueError("invalid verdict fields")
            if record["ok"]:
                if not record["text"].strip() or record["error"] is not None or record["error_kind"] is not None:
                    raise ValueError("inconsistent successful result")
            elif not record["error"] or record["text"]:
                raise ValueError("inconsistent failed result")
        # Ensure the saved prompt is present before login or any judge is invoked.
        (run_dir / "prompt.md").read_text(encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, OverflowError) as exc:
        raise RuntimeError(f"Cannot resume saved run: {exc}. "
                           "Older runs without a run.json manifest need a fresh consultation.") from exc
    for path in paths:
        if not Path(path).is_dir():
            raise RuntimeError(f"Original workspace folder is missing: {path}")
    return state


def resume_consult(run_dir: Path, config: Config, login: bool = False) -> tuple[Path, list["Verdict"]]:
    """Retry each failed judge once, using the original prompt and workspace."""
    from .run import _execute, _pre_run

    run_dir = Path(os.path.abspath(Path(run_dir).expanduser()))
    if not run_dir.is_dir():
        raise RuntimeError(f"Cannot resume saved run: directory not found: {run_dir}")
    with run_lock(run_dir):
        state = load_run(run_dir)
        if login and not any(v["judge"] == "claude" and not v["ok"]
                             and v["error_kind"] == "authentication_required" for v in state["verdicts"]):
            raise RuntimeError("This saved run has no failed Claude sign-in to recover. "
                               "Resume without --login to retry other failures.")
        if any(not result["ok"] for result in state["verdicts"]):
            _pre_run(config)
        if login:
            from .auth import login_claude
            login_claude(config, state["cwd"])
        return run_dir, _execute(run_dir, state, config)
