"""Conservative sign-in hints for failures reported by the Claude CLI."""

import json
import subprocess
import sys

from .config import Config
from .discover import find_cli


def authentication_error(judge: str, stdout: str, stderr: str) -> bool:
    """Classify failed requests only; successful verdict prose is not an error."""
    if judge != "claude":
        return False
    text = f"{stdout}\n{stderr}".lower()
    return any(marker in text for marker in (
        "login expired", "oauth session expired and could not be refreshed",
        "oauth token has expired", "oauth token revoked",
        "not logged in · please run /login",
    ))


def login_claude(config: Config, cwd: str) -> None:
    """Run an explicitly requested subscription login in the caller's terminal."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise RuntimeError("--login needs an interactive terminal. Run "
                           "`claude auth login --claudeai` in your terminal, then resume without --login.")
    cli = find_cli("claude", config)
    if cli is None:
        raise RuntimeError("Claude CLI not found; restore it before signing in.")
    try:
        # Deliberately inherit terminal input/output; never capture login codes.
        result = subprocess.run([cli, "auth", "login", "--claudeai"], cwd=cwd, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Claude sign-in did not finish. Saved verdicts are preserved; "
                           "sign in in your terminal, then resume.") from exc
    if result.returncode != 0:
        raise RuntimeError("Claude sign-in did not finish. Saved verdicts are preserved; "
                           "sign in in your terminal, then resume.")
    try:
        status = subprocess.run([cli, "auth", "status", "--json"], cwd=cwd,
                                capture_output=True, text=True, timeout=30)
        data = json.loads(status.stdout)
        if (status.returncode != 0 or not isinstance(data, dict)
                or data.get("loggedIn") is not True or data.get("authMethod") != "claude.ai"):
            raise ValueError("subscription login is not active")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Could not verify subscription authentication. Check "
                           "`claude auth status --text` for credential overrides or CLI support "
                           "before resuming. Saved verdicts are preserved.") from exc
