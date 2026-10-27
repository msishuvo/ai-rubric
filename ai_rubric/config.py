"""Optional user config. Models and efforts are deliberately not configurable."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".config" / "ai-rubric" / "config.toml"
DEFAULT_SAVE_ROOT = str(Path.home() / ".local" / "state" / "ai-rubric" / "consultations")
PINNED_KEYS = {"model", "effort", "models", "reasoning_effort"}


@dataclass
class Config:
    cli_paths: dict[str, str] = field(default_factory=dict)
    extra_dirs: list[str] = field(default_factory=list)
    timeout: int = 1200
    save_root: str = DEFAULT_SAVE_ROOT
    pre_run: list[str] | None = None


def _expand(p: str) -> str:
    return str(Path(p).expanduser())


def _reject_pinned(table: dict, where: str) -> None:
    for key, value in table.items():
        if key in PINNED_KEYS:
            raise ValueError(f"{where}{key}: models are pinned and cannot be set in config")
        if isinstance(value, dict):
            _reject_pinned(value, f"{where}{key}.")


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG
    if not path.is_file():
        return Config()
    data = tomllib.loads(path.read_text())
    _reject_pinned(data, "")
    cfg = Config()
    if "timeout" in data:
        cfg.timeout = int(data["timeout"])
    if "save_root" in data:
        cfg.save_root = _expand(data["save_root"])
    cfg.extra_dirs = [_expand(d) for d in data.get("extra_dirs", [])]
    if "pre_run" in data:
        cfg.pre_run = [str(a) for a in data["pre_run"]]
    cfg.cli_paths = {k: _expand(v) for k, v in data.get("cli", {}).items()}
    return cfg
