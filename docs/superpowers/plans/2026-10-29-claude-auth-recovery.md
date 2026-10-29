# Claude authentication recovery implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Explain expired Claude subscription sign-ins and resume only failed judges after user-controlled sign-in.

**Architecture:** Classify Claude authentication failures at the subprocess boundary. Checkpoint the saved prompt, original workspace roots, and each judge result in a versioned manifest. An explicit resume action preserves successful verdicts and optionally performs interactive subscription login before retrying failed judges once.

**Tech Stack:** Python 3.11+, standard library, unittest and executable fake CLIs.

**Spec:** The recovery flow approved in this chat on 2026-10-29; the neutral brief is `/tmp/consult-auth-recovery-brief.md`.

## Global constraints

- Preserve pinned models, judge assignments, subscription billing, and existing exit codes.
- No credential extraction, custom refresh logic, automatic model substitution, or repeated authentication retries.
- Login must inherit a real terminal; unattended runs print recovery instructions without launching login.
- Status after login is diagnostic; the actual retried judge request is definitive.
- Resume reuses the exact saved prompt and roots; disclose that the workspace is live and older verdicts may reflect earlier files.
- User approved implementation and consultation; proceed inline without another approval round. Keep changes reviewable and do not publish.

## Review focus

- Authentication text on stdout when stderr also contains unrelated warnings: classify the actual failure.
- Text quoted in an otherwise successful verdict: never treat a discussion of authentication as a failed request.
- Interrupted consultations and multiple resume invocations: checkpoint results and prevent concurrent retries.
- Malformed/old manifests and missing workspace folders: actionable errors before invoking judges or login.
- Failed login, unsupported status, or another credential source: preserve completed work and do not silently change authentication/billing.

### Task 1: Identify Claude sign-in failures

**Files:** Create `ai_rubric/auth.py`, `tests/test_auth.py`; modify `ai_rubric/run.py`, `tests/test_run.py`.

**Interfaces:** `authentication_error(judge: str, stdout: str, stderr: str) -> bool`; `Verdict.error_kind: str | None = None`.

- [x] Write table-driven classification tests for rejected renewal, expired/revoked tokens, unrelated errors, other judges, and real fake-CLI output with both streams.
- [x] Run new tests; expect missing classification/metadata failures.
- [x] Add narrow Claude-specific classification for nonzero judge exits; do not inspect successful verdict prose.
- [x] Run authentication and runner tests, then the full suite with Python 3.12 on PATH; expect zero failures.

### Task 2: Checkpoint and resume failed judges

**Files:** Create `ai_rubric/recovery.py`, `tests/test_recovery.py`; modify `ai_rubric/run.py`.

**Interfaces:** `resume_consult(run_dir: Path, config: Config) -> tuple[Path, list[Verdict]]`. Version 1 `run.json` contains host, absolute cwd, extra roots, and serialized verdicts. Pinned judge identities are validated against `judges_for(host)`.

- [x] Write fake-CLI tests proving successful verdict bytes/mtime stay unchanged, exact prompt/cwd/roots are reused, only failed judges rerun, retries happen once, and partial progress survives interruption.
- [x] Add validation/lock tests for malformed manifests, changed pinned identities, absent roots, all-success no-op, concurrent resume, and a stale output file from a failed attempt.
- [x] Run new tests; expect missing resume/checkpoint failures.
- [x] Implement atomic manifest checkpoints as futures complete; save initial pending states before starting. Remove stale per-judge output files before retry. Resume uses current timeout/CLI discovery and original saved context.
- [x] Run recovery and runner tests, then the full suite; expect zero failures.

### Task 3: Expose guided login and resume

**Files:** Modify `ai_rubric/cli.py`, `ai_rubric/auth.py`, `tests/test_cli.py`, `tests/test_auth.py`, `README.md`.

**Interfaces:** Existing fresh invocation remains supported; add `consult --resume DIR [--login]`. `--login` requires a failed Claude authentication result and real input/output terminals. Invoke discovered CLI as `auth login --claudeai`, inherit terminal input/output, then inspect `auth status --json` without printing account details. An unsuccessful verification leaves saved results intact.

- [x] Write CLI integration tests for recovery instructions, argument combinations, explicit partial labeling, noninteractive refusal, login failure, subscription status verification, and successful login followed by one failed-judge retry.
- [x] Run new tests; expect missing flags/recovery failures.
- [x] Implement guarded interactive login, resume output with live-workspace warning, and shell-quoted recovery commands. Document manual and assisted recovery and existing-run limitations.
- [x] Run the full suite and CLI help; expect zero failures and documented flags.
- [x] Request one independent whole-change code review, address important findings with regression tests, and perform final verification.

## Execution record

- Baseline: 75 tests pass with `PATH=/opt/miniconda3/bin:$PATH python3 -m unittest discover -s tests`.
- Independent consultation completed; both judges recommended a narrower flow and raised live-workspace drift. No routine preflight; disclose drift and keep explicit post-login auth-source verification.
- Independent code review completed; the important checkpoint-ordering finding was reproduced and fixed with regression tests. Final worktree suite: 106 tests passed.
