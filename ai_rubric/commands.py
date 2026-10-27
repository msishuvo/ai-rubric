"""Exact read-only argv for each judge. Never built as a shell string."""

from .judges import Judge


def _add_dirs(dirs: list[str]) -> list[str]:
    return [arg for d in dirs for arg in ("--add-dir", d)]


def build_command(judge: Judge, cli: str, prompt: str, cwd: str,
                  add_dirs: list[str], out_file: str) -> list[str]:
    if judge.name == "claude":
        return [cli, "-p", prompt, "--model", judge.model, "--effort", judge.effort,
                "--permission-mode", "plan", "--output-format", "text"] + _add_dirs(add_dirs)
    if judge.name == "codex":
        # No --add-dir: in Codex it grants write access. Extra folders reach Codex
        # through the prompt's folder list; the read-only sandbox can read them.
        return [cli, "exec", "-m", judge.model,
                "-c", f'model_reasoning_effort="{judge.effort}"',
                "-s", "read-only", "-C", cwd, "--skip-git-repo-check", "--ephemeral",
                "-o", out_file, prompt]
    if judge.name == "agy":
        return [cli, "-p", prompt, "--model", judge.model, "--mode", "plan",
                "--output-format", "text"] + _add_dirs(add_dirs)
    raise ValueError(f"no command for judge {judge.name!r}")
