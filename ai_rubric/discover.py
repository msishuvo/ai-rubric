"""Find each judge's CLI: config path, then PATH, then known install locations."""

import os
import shutil
from pathlib import Path

from .config import Config

_LOCAL_BIN = Path.home() / ".local" / "bin"

KNOWN_LOCATIONS: dict[str, list[str]] = {
    "claude": [str(_LOCAL_BIN / "claude")],
    "agy": [str(_LOCAL_BIN / "agy")],
    "codex": [
        str(_LOCAL_BIN / "codex"),
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
    ],
}


def _executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def find_cli(name: str, config: Config) -> str | None:
    configured = config.cli_paths.get(name)
    if configured and _executable(configured):
        return configured
    on_path = shutil.which(name)
    if on_path:
        return on_path
    for candidate in KNOWN_LOCATIONS.get(name, []):
        if _executable(candidate):
            return candidate
    return None
