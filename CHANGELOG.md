# Changelog

Versions follow semantic versioning: patch for fixes, minor for new behavior,
major when saved runs stop resuming or the installed files change. To release:
bump `__version__` in `ai_rubric/__init__.py`, add an entry here, commit, then
`git tag -a v<version> -m "consult <version>"` and `git push origin v<version>`.
A pushed tag does not make a GitHub release; publish one with that version's
entry from this file as its notes:
`gh release create v<version> --verify-tag --title "consult <version>" --notes-file <entry.md>`.
Each saved run records the version that made it (`tool_version` in `run.json`).

## 1.1.0 - 2026-11-26

- Antigravity is a host: `consult --from agy` asks Claude `claude-opus-5-5`
  and Codex `gpt-6.2-astra`.
- From Antigravity, a usage-limited slot gets `gemini-4-carbon-high`; if both
  slots hit their limit, the second gets `gemini-4-neon-high`. Claude Code and
  Codex hosts are unchanged.
- The installer links an Antigravity plugin folder for the skill
  (`~/.gemini/config/plugins/ai-rubric`) and adds the "use consult" rule to
  `~/.gemini/GEMINI.md`.
- The stand-in note names the model that ran.
- Judges are told not to use the consult skill themselves.
- Fix: a run cancelled right after a usage limit can be resumed.

## 1.0.0 - 2026-11-25

First tagged release.

- Judges: Codex `gpt-6.2-astra` or Claude `claude-opus-5-5` (the other host's
  model) plus Antigravity `gemini-4-carbon-high`, all at high effort.
- If Astra or Opus fails because it hit its usage limit, `gemini-4-neon-high`
  runs in its place, so a run still gets two verdicts.
- Ctrl-C, SIGTERM and SIGHUP stop every judge at once and print the
  `consult --resume` command; a hangup ignored at start (`nohup`) stays ignored.
- `--resume` retries only failed judges; `--login` guides a Claude sign-in.
- The installer writes config files atomically, checks Antigravity's settings
  before changing anything, and can still uninstall when they are broken.
- `consult --version` prints the version.

Breaking: runs saved before 1.0.0 cannot be resumed (the judge models changed);
start a fresh consultation.
