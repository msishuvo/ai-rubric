# ai-rubric council Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `consult` skill and script that, from Claude Code or Codex, gets blind, two-sided verdicts on a proposal from the other two pinned judges (Claude Opus 5.5 medium, GPT-6 Astra medium, Gemini 4 Argon high).

**Architecture:** A small Python package (`ai_rubric/`) does judge selection, CLI discovery, prompt assembly, a neutrality lint, command building and parallel runs; `bin/consult` is its entry point. One `skills/consult/SKILL.md` serves both hosts. `install.sh` links the skill and script and writes marked rule blocks into each tool's global files.

**Tech Stack:** Python 3.11+ standard library only (`tomllib`, `subprocess`, `concurrent.futures`, `unittest`); POSIX `bash` for `install.sh`.

**Spec:** `docs/superpowers/specs/2026-10-27-ai-rubric-council-design.md`

## Global Constraints

- Standard library only. No pip, no venv. Python 3.11+ (needs `tomllib`); `bin/consult` exits 2 with a clear message on older Python.
- Judges are pinned and not configurable:
  - `claude`: model `claude-opus-5-5`, effort `medium`
  - `codex`: model `gpt-6-astra`, effort `medium`
  - `agy`: model `gemini-4-argon-high` (effort is in the id)
- Host `claude` → judges `codex`, `agy`. Host `codex` → judges `claude`, `agy`. Any other host value is an error.
- Never substitute a judge, model or effort. A missing CLI or failed run is reported as that judge failing.
- Judges run read-only. No judge command may include a write-enabling flag.
- Every subprocess is called with an argv list, never `shell=True`.
- Default timeout 1200 seconds per judge.
- Default save root `~/.local/state/ai-rubric/consultations/`. Default config `~/.config/ai-rubric/config.toml`.
- Install markers exactly `<!-- ai-rubric start -->` / `<!-- ai-rubric end -->` (markdown files) and `# ai-rubric start` / `# ai-rubric end` (Codex rules file).
- Nothing in the repo mentions a specific project of the owner's.

## Review Focus

1. A brief containing quotes, `$`, backticks, newlines, non-ASCII and 50 KB of text reaches every judge byte-for-byte (Task 4 test).
2. A workspace path containing spaces works for `--add-dir` and for the folder list in the prompt (Task 4 test).
3. One judge hangs: it is killed at the timeout, reported failed, and the other judge's verdict is still saved and printed (Task 5 test).
4. A judge exits 0 with empty or whitespace-only output (typically not logged in): reported as failed, not as an empty verdict (Task 5 test).
5. `install.sh` run twice, or against a CLAUDE.md with existing content, leaves exactly one block and every byte outside the markers unchanged; a missing target file is created (Task 8 test).

---

### Task 1: Clear Rubric out and add judge selection

**Files:**
- Delete: `hooks/`, `presets/`, `rubric/`, `scripts/`, `skills/setup/`, `.claude-plugin/`, `tests/*` (all old), `docs/superpowers/specs/2026-09-03-rubric-design.md`, `docs/superpowers/plans/2026-09-03-rubric.md`, `README.md`
- Create: `ai_rubric/__init__.py`, `ai_rubric/judges.py`, `tests/__init__.py`, `tests/test_judges.py`
- Modify: `.gitignore` (keep `__pycache__/`)

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Judge: name: str; model: str; effort: str | None` and `judges_for(host: str) -> list[Judge]` (raises `ValueError` for an unknown host). `JUDGES: dict[str, Judge]` keyed `"claude"`, `"codex"`, `"agy"`.

- [ ] **Step 1: Delete the Rubric files listed above** (`git rm -r`). Run `git status`; expected: only deletions plus `docs/superpowers/specs/2026-10-27-…` and this plan.
- [ ] **Step 2: Write failing tests** in `tests/test_judges.py`:
  - `test_claude_host_gets_codex_and_agy`: `[j.name for j in judges_for("claude")] == ["codex", "agy"]`
  - `test_codex_host_gets_claude_and_agy`: `== ["claude", "agy"]`
  - `test_models_are_pinned`: `JUDGES["claude"] == Judge("claude", "claude-opus-5-5", "medium")`, `JUDGES["codex"] == Judge("codex", "gpt-6-astra", "medium")`, `JUDGES["agy"] == Judge("agy", "gemini-4-argon-high", None)`
  - `test_unknown_host_rejected`: `judges_for("agy")` and `judges_for("gemini")` raise `ValueError`
- [ ] **Step 3: Run** `python3 -m unittest tests.test_judges -v`. Expected: FAIL (import error).
- [ ] **Step 4: Implement `ai_rubric/judges.py`.**
- [ ] **Step 5: Run** the same command. Expected: 4 tests OK.
- [ ] **Step 6: Commit** `git commit -m "Replace Rubric with the council's judge selection"`.

### Task 2: Config and CLI discovery

**Files:**
- Create: `ai_rubric/config.py`, `ai_rubric/discover.py`, `tests/test_config.py`, `tests/test_discover.py`

**Interfaces:**
- Produces:
  - `@dataclass class Config: cli_paths: dict[str, str]; extra_dirs: list[str]; timeout: int = 1200; save_root: str; pre_run: list[str] | None = None`
  - `load_config(path: Path | None = None) -> Config`. Missing file gives defaults. Keys in TOML: `timeout`, `save_root`, `extra_dirs`, `pre_run` (argv list), and table `[cli]` with `claude`, `codex`, `agy`. Any `model`/`effort` key raises `ValueError("models are pinned …")`. `~` is expanded.
  - `KNOWN_LOCATIONS: dict[str, list[str]]`: `~/.local/bin/<name>` for all three (on the owner's Mac, `claude`, `codex` and `agy` all live there), then `"codex": ["/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"]` as a last resort.
  - `find_cli(name: str, config: Config) -> str | None`. Order: `config.cli_paths[name]` if executable → `shutil.which(name)` → `KNOWN_LOCATIONS`.

- [ ] **Step 1: Write failing tests:**
  - `test_missing_config_gives_defaults`: `timeout == 1200`, `save_root` ends with `.local/state/ai-rubric/consultations`, `extra_dirs == []`
  - `test_config_values_read` from a temp TOML with `timeout = 60`, `extra_dirs = ["~/x"]`, `[cli] codex = "/tmp/fake"`
  - `test_model_key_rejected`: TOML with `model = "x"` raises `ValueError`
  - `test_find_cli_prefers_config_path`, `test_find_cli_falls_back_to_path` (temp dir on `PATH` with an executable `agy`), `test_find_cli_known_location` (patch `KNOWN_LOCATIONS`), `test_find_cli_missing_returns_none`, `test_non_executable_config_path_skipped`
- [ ] **Step 2: Run** `python3 -m unittest tests.test_config tests.test_discover -v`. Expected: FAIL.
- [ ] **Step 3: Implement both modules.**
- [ ] **Step 4: Run** again. Expected: all OK.
- [ ] **Step 5: Commit** `"Load config and find each judge's CLI"`.

### Task 3: Judge prompt and neutrality lint

**Files:**
- Create: `ai_rubric/prompt.py`, `tests/test_prompt.py`

**Interfaces:**
- Produces:
  - `JUDGE_INSTRUCTIONS: str`: the fixed instructions from the spec's "What each judge does" section. It must contain the six headings verbatim: `## Case for`, `## Case against`, `## Verdict`, `## Missing`, `## Evidence`, `## Not checked`. It says to read the workspace, not edit anything, treat the brief's files as a start, and give the verdict as one of keep / change / drop with a confidence.
  - `build_prompt(brief: str, roots: list[str]) -> str`: instructions, then a "Workspace folders you may read" list (one absolute path per line), then the brief unchanged.
  - `lint_brief(brief: str) -> list[str]`: returns the matched phrases that leak authorship or leaning. Case-insensitive, whole words. Patterns: `\b(claude|codex|antigravity|gemini|gpt|opus|chatgpt)\b`, `\bI (feel|think|believe|suspect|doubt|prefer|like|hate)\b`, `\b(my|our) (proposal|plan|idea|answer|design)\b`, `\buser (thinks|feels|prefers|wants to drop|doubts)\b`, `\b(you|I) (wrote|proposed|suggested)\b`.

- [ ] **Step 1: Write failing tests:**
  - `test_prompt_has_all_headings`: each of the six headings is in `build_prompt("b", ["/w"])`
  - `test_prompt_lists_roots_and_keeps_brief`: roots `["/a b", "/c"]` each on its own line; the brief appears verbatim at the end
  - `test_lint_flags_tool_names`: `lint_brief("Codex agreed with this")` contains `"Codex"`
  - `test_lint_flags_leaning`: `"I feel this plan is weak"` gives a hit
  - `test_lint_flags_authorship`: `"Review my proposal"` gives a hit
  - `test_lint_clean_brief`: `"Is this pricing plan worth shipping? Argue both ways."` gives `[]`
  - `test_lint_ignores_substrings`: `"gptools directory"` gives `[]`
- [ ] **Step 2: Run** `python3 -m unittest tests.test_prompt -v`. Expected: FAIL.
- [ ] **Step 3: Implement `ai_rubric/prompt.py`.**
- [ ] **Step 4: Run.** Expected: OK.
- [ ] **Step 5: Commit** `"Build the judge prompt and lint briefs for leaks"`.

### Task 4: Per-CLI command building

**Files:**
- Create: `ai_rubric/commands.py`, `tests/test_commands.py`

**Interfaces:**
- Consumes: `Judge` (Task 1).
- Produces: `build_command(judge: Judge, cli: str, prompt: str, cwd: str, add_dirs: list[str], out_file: str) -> list[str]`. Exact argv:
  - claude: `[cli, "-p", prompt, "--model", "claude-opus-5-5", "--effort", "medium", "--permission-mode", "plan", "--output-format", "text"] + ["--add-dir", d for d in add_dirs]`
  - codex: `[cli, "exec", "-m", "gpt-6-astra", "-c", 'model_reasoning_effort="medium"', "-s", "read-only", "-C", cwd, "--skip-git-repo-check", "--ephemeral", "-o", out_file, prompt]`. No `--add-dir`, because in Codex it grants write access. Extra folders reach Codex only through the prompt's folder list (read-only sandbox can read them).
  - agy: `[cli, "-p", prompt, "--model", "gemini-4-argon-high", "--mode", "plan", "--output-format", "text"] + ["--add-dir", d for d in add_dirs]`
  - `out_file` is used only by codex; the runner takes other judges' stdout.

- [ ] **Step 1: Write failing tests:**
  - one test per judge asserting the exact argv above for `add_dirs=["/x y", "/z"]`
  - `test_prompt_is_single_argv_element`: prompt `'a "b" $c `d`\nüñ' + "x"*50000` appears as exactly one unchanged element (Review Focus 1)
  - `test_no_write_flags`: no argv contains `workspace-write`, `danger-full-access`, `acceptEdits`, `bypassPermissions`, `accept-edits`, `--dangerously-skip-permissions`
- [ ] **Step 2: Run** `python3 -m unittest tests.test_commands -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: OK.
- [ ] **Step 5: Commit** `"Build read-only commands for each judge"`.

### Task 5: Parallel runner and saved consultation

**Files:**
- Create: `ai_rubric/run.py`, `tests/test_run.py`, `tests/fakes/` (tiny executable scripts used as fake CLIs)

**Interfaces:**
- Consumes: `judges_for`, `find_cli`, `Config`, `build_prompt`, `build_command`.
- Produces:
  - `@dataclass class Verdict: judge: str; model: str; ok: bool; text: str; error: str | None; seconds: float`
  - `make_run_dir(save_root: str, brief: str, now: datetime) -> Path`: `<save_root>/<YYYYmmdd-HHMMSS>-<slug>`. The slug is the first 6 words of the brief's first non-empty line, lowercased, non-alphanumerics replaced by `-`, max 40 chars.
  - `run_consult(host: str, brief: str, cwd: str, add_dirs: list[str], config: Config) -> tuple[Path, list[Verdict]]`. It writes `brief.md`, `prompt.md`, `<judge>.md` (verdict text or `FAILED: <error>`), and `run.log` (argv minus the prompt, exit code, seconds per judge).
  - Behavior: if `config.pre_run` is set, run it first; a non-zero exit aborts with `RuntimeError` naming the command. Roots = `[cwd] + add_dirs + config.extra_dirs`, de-duplicated, absolute. Both judges start together (`ThreadPoolExecutor(max_workers=2)`, `subprocess.run(..., timeout=config.timeout, capture_output=True)`). Text = codex's `out_file` contents, otherwise stdout. `ok=False` when the CLI is not found (`error="<name> CLI not found"`), on timeout (`error="timed out after <n>s"`), on non-zero exit (`error` = last 20 lines of stderr), or when the text is empty or whitespace only (`error="empty verdict"`).

- [ ] **Step 1: Write failing tests** using fake CLIs placed via `Config.cli_paths`:
  - `test_both_judges_succeed`: fakes echo `## Verdict\nkeep`; both `ok`; files `brief.md`, `prompt.md`, `codex.md`, `agy.md`, `run.log` exist
  - `test_missing_cli_reported_not_substituted`: codex path missing and not on `PATH` (patch `KNOWN_LOCATIONS` empty). The codex verdict has `ok=False` and `"not found"` in its error, and no claude verdict exists
  - `test_hanging_judge_times_out_other_saved`: agy fake sleeps 30s with `timeout=2`. agy fails with `"timed out"`, codex is `ok`, and total time is under 10s (Review Focus 3)
  - `test_empty_output_is_failure`: fake prints `"  \n"` and exits 0, giving `ok=False, error="empty verdict"` (Review Focus 4)
  - `test_nonzero_exit_captures_stderr`
  - `test_pre_run_failure_aborts`: `pre_run=["false"]` raises `RuntimeError`
  - `test_roots_deduplicated_and_absolute`
  - `test_slug`: `make_run_dir(root, "Is this Plan worth it? yes", fixed_now).name == "20261027-101500-is-this-plan-worth-it-yes"`
- [ ] **Step 2: Run** `python3 -m unittest tests.test_run -v`. Expected: FAIL.
- [ ] **Step 3: Implement `ai_rubric/run.py`.**
- [ ] **Step 4: Run.** Expected: OK.
- [ ] **Step 5: Commit** `"Run both judges in parallel and save the consultation"`.

### Task 6: `consult` command

**Files:**
- Create: `ai_rubric/cli.py`, `bin/consult` (executable), `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config`, `lint_brief`, `run_consult`.
- Produces: `main(argv: list[str]) -> int`. Usage `consult --from {claude,codex} --brief FILE [--add-dir DIR]... [--allow-flagged] [--config FILE]`.
  - Lint hits without `--allow-flagged` print `Brief may reveal authorship or leaning: <hits>. Rewrite it neutrally, or pass --allow-flagged if these words are part of the subject itself.` to stderr and return 3. No judge runs.
  - Otherwise it prints to stdout, per judge in order: `=== <judge> (<model>) — ok|FAILED ===` then the text or error, then a final line `Saved: <run dir>`.
  - Exit codes: 0 if at least one judge ok, 1 if both failed, 2 usage/config/Python-version error, 3 lint refusal.
  - `bin/consult` resolves its own real path (following symlinks), puts the repo root on `sys.path`, checks `sys.version_info >= (3, 11)`, and calls `main`.

- [ ] **Step 1: Write failing tests:**
  - `test_lint_refusal_exit_3_no_run` (patch `run_consult`, assert not called)
  - `test_allow_flagged_runs`
  - `test_output_format_and_exit_0` (patch `run_consult` to return one ok and one failed verdict)
  - `test_both_failed_exit_1`
  - `test_bad_host_exit_2`
  - `test_bin_works_through_symlink`: symlink `bin/consult` into a temp dir and run it with `--help`, giving exit 0
- [ ] **Step 2: Run** `python3 -m unittest tests.test_cli -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite `python3 -m unittest discover -s tests -t . -v`. Expected: all OK.
- [ ] **Step 5: Commit** `"Add the consult command"`.

### Task 7: The `consult` skill

**Files:**
- Create: `skills/consult/SKILL.md`, `tests/test_skill.py`

**Interfaces:**
- Consumes: the `consult` command contract (Task 6).

Frontmatter `name: consult`. The `description` says when to use it: an independent second opinion could change the outcome (design, UI, architecture, product or pricing scope, choosing between options, reviewing a plan or proposal from anyone), or the user says "consult", "council this" or `/consult`. It also says when not to: factual lookups, explaining code, small edits, bugs with a clear cause, or the user says "no council". The body covers, in order:
1. Which `--from` value you are: Claude Code → `claude`, Codex → `codex`.
2. Brief checklist, copied from the spec's "The brief" section, including the excluded items and the neutral rewrite of a doubt.
3. Write the brief to a temp file and run `consult --from <you> --brief <file> [--add-dir …]` for every workspace folder outside the current one. Run it in the background or with a long timeout, since it can take up to 20 minutes. In Codex the command needs to run outside the sandbox; the install adds a rule for it.
4. On exit 3, rewrite the brief. Don't reach for `--allow-flagged` unless the flagged words are the subject itself.
5. Report in the spec's "What the owner sees" order. State unresolved disagreement as unresolved. Never claim agreement the verdicts don't show.
6. If a judge failed, say which one and why. Never run a substitute model.

- [ ] **Step 1: Write failing test** `test_skill_frontmatter`: the file parses as `---` YAML-ish frontmatter with `name: consult` and a `description` under 1024 chars that contains `consult` and `no council`. The body contains `--from claude`, `--from codex` and `--allow-flagged`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_skill -v`. Expected: FAIL.
- [ ] **Step 3: Write `skills/consult/SKILL.md`.**
- [ ] **Step 4: Run.** Expected: OK.
- [ ] **Step 5: Commit** `"Add the consult skill"`.

### Task 8: `install.sh`

**Files:**
- Create: `install.sh` (executable), `install/claude-rule.md`, `install/gemini-rules.md`, `install/codex.rules`, `tests/test_install.py`

**Interfaces:**
- Produces: `install.sh [--uninstall]`, honouring `$HOME`. The tests run it with a temp `HOME`.
  - Symlinks: `$HOME/.claude/skills/consult` → `<repo>/skills/consult`; `$HOME/.codex/skills/consult` → same; `$HOME/.local/bin/consult` → `<repo>/bin/consult`. It creates parent folders. An existing non-symlink at a target is left alone, with a warning, and the script exits 1 at the end.
  - Marked blocks (replaced in place if present, appended with a blank line before if absent, file created if missing):
    - `install/claude-rule.md` into `$HOME/.claude/CLAUDE.md` and `$HOME/.codex/AGENTS.md`. Content: when to use `consult` and when not, and that the judges and models are fixed.
    - `install/gemini-rules.md` into `$HOME/.gemini/GEMINI.md`. Content: read files before asserting, never invent, cite paths, state what was not checked, don't edit when judging.
    - `install/codex.rules` into `$HOME/.codex/rules/default.rules` with `#` markers, containing `prefix_rule(pattern=["consult"], decision="allow")`.
  - Reports each CLI (`claude`, `agy`, and codex via `PATH` or the ChatGPT.app path) as found or `MISSING`, and warns if `$HOME/.local/bin` is not on `PATH`.
  - `--uninstall` removes only symlinks that point into this repo and only the marked blocks.

- [ ] **Step 1: Write failing tests:**
  - `test_install_creates_links_and_blocks`
  - `test_install_twice_is_idempotent`: byte-identical files after the second run (Review Focus 5)
  - `test_existing_content_preserved`: pre-seed CLAUDE.md with `"# Mine\nkeep\n"`; after install it starts with exactly that, and after `--uninstall` it equals it exactly (Review Focus 5)
  - `test_block_replaced_not_duplicated`: change `install/claude-rule.md` in a temp repo copy and reinstall, giving one block with the new text
  - `test_real_file_at_link_target_not_overwritten`: exit 1, file unchanged
  - `test_uninstall_leaves_foreign_symlinks`
- [ ] **Step 2: Run** `python3 -m unittest tests.test_install -v`. Expected: FAIL.
- [ ] **Step 3: Write `install.sh` and the three install fragments.**
- [ ] **Step 4: Run** the full suite. Expected: all OK.
- [ ] **Step 5: Commit** `"Add the installer"`.

### Task 9: README and live verification

**Files:**
- Create: `README.md`

README sections: what it is (two sentences); judges table; install (`git clone … && ./install.sh`); when it runs, and how to force or skip it; where results go; config keys; exit codes; uninstall; `rubric-final` tag for the old plugin; running tests.

- [ ] **Step 1: Write README.md.** Commit `"Document ai-rubric"`.
- [ ] **Step 2: Install for real on this Mac:** run `./install.sh`. Expected: all three CLIs found, and the links and blocks in place. Show `git diff --no-index` style before/after of `~/.claude/CLAUDE.md` to the owner.
- [ ] **Step 3: Live run from Claude Code.** In this repo, run `consult --from claude --brief <neutral brief asking whether this repo's install.sh design is sound>`. Expected: `codex` and `agy` both ok. Both verdicts have the six headings and cite files from this repo. Check `run.log` and the verdicts to confirm which models actually ran. If `--permission-mode plan` or `--mode plan` blocks reading in print mode, fix it in Task 4 (a test update plus the code) and record the reason.
- [ ] **Step 4: Live run from Codex.** In a Codex session, ask a design question that should trigger the skill. Expected: the skill fires and calls `consult --from codex`, claude and agy are ok, and the sandbox rule lets it run without a prompt. If Codex doesn't load `~/.codex/skills/`, find the location this version reads, then update `install.sh` and its test.
- [ ] **Step 5: Negative check:** ask a plain factual question in each host. Expected: no consult run.
- [ ] **Step 6: Remote server:** the owner runs `git pull && ./install.sh` there, then one live consult. Record the result in the README's observed-behavior note, or record it as not yet verified.
- [ ] **Step 7: Commit** any fixes and push `main`.
