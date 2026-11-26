# Antigravity Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `consult --from agy` runs Claude Opus and GPT Astra as judges, with Gemini standing in on a usage limit.

**Architecture:** Add `agy` to `HOSTS`; replace the single `FALLBACK` with a per-host ordered stand-in list that slots claim first-come under a lock. Resume validation, stale-export cleanup and the CLI note follow the list. The installer links a small Antigravity plugin folder for the skill and adds the "use consult" rule to GEMINI.md.

**Tech Stack:** Python 3.11 stdlib, bash installer, unittest.

**Spec:** `docs/superpowers/specs/2026-11-26-antigravity-host-design.md`

## Global Constraints

- Models pinned: `claude-opus-5-5` (high), `gpt-6.2-astra` (high), `gemini-4-carbon-high`, `gemini-4-neon-high`.
- Stand-in only when the slot's error_kind is `usage_limit`.
- Claude/Codex hosts unchanged: stand-ins `[neon]`.
- Agy host: judges `[claude, codex]`, stand-ins `[agy (Carbon), neon]`, claimed in that order.
- Manifest `version` stays 1. Bump `__version__` to `1.1.0`.

## Review Focus

- Both slots hit the limit at once → one gets Carbon, the other Neon, never the same model twice.
- Resume after one slot already holds Carbon and the other slot hits a limit → that slot gets Neon.
- Resume of an agy-host run whose slot holds `agy` or `neon` → manifest validates.
- A slot record saved with `error_kind == "usage_limit"` (cancel before stand-in) → resume still validates.
- Installer twice / uninstall → plugin link created once, removed cleanly, foreign link left alone.

---

### Task 1: Judges and stand-ins per host

**Files:** Modify `ai_rubric/judges.py`; Test `tests/test_judges.py`

**Interfaces — Produces:** `HOSTS = ("claude", "codex", "agy")`; `judges_for(host) -> list[Judge]`; `stand_ins_for(host) -> list[Judge]`; keep `FALLBACK` (Neon) as a name.

- [ ] Tests: `judges_for("agy")` names == `["claude", "codex"]`; `stand_ins_for("claude")` and `("codex")` == `[FALLBACK]`; `stand_ins_for("agy")` == `[JUDGES["agy"], FALLBACK]`; unknown-host test drops `"agy"`.
- [ ] Run `python3 -m unittest tests.test_judges -v` → FAIL; implement; → PASS.

### Task 2: Run and resume with claimed stand-ins

**Files:** Modify `ai_rubric/run.py`, `ai_rubric/recovery.py`; Test `tests/test_run.py`, `tests/test_recovery.py`

**Interfaces — Consumes:** `stand_ins_for`. **Produces:** `_run_slot(judge, config, prompt, cwd, add_dirs, run_dir, log, claim: Callable[[], Judge | None])`.

- [ ] Tests (fake CLIs as in existing tests):
  - `test_agy_host_gets_claude_and_codex`: both succeed, judges `["claude", "codex"]`.
  - `test_agy_host_usage_limit_brings_in_carbon`: codex limited → verdicts `[("claude",…), ("agy","gemini-4-carbon-high",True)]`, `agy.md` exists.
  - `test_agy_host_both_limited_get_carbon_and_neon`: both limited → set of judges `{"agy","neon"}`.
  - `test_agy_resume_after_carbon_held_gives_neon`: run with codex limited, claude failing (connection reset); then make claude limited and resume → `[neon, agy]`.
  - recovery: a manifest with agy host and slot judges `agy`/`neon` validates; a record with `error_kind "usage_limit"` validates.
  - update `test_no_stand_in_after_interrupt` to pass `claim`.
- [ ] Implement: in `_execute`, `available = [s for s in stand_ins_for(host) if s.name not in {state["verdicts"][i]["judge"] for i not pending}]`; `claim()` pops `available[0]` under a `threading.Lock`, returns None when empty. `_run_slot` uses it. `_drop_stale_exports` covers all `stand_ins_for(host)` names. Recovery: any slot may hold a stand-in name; allow `"usage_limit"` error_kind.
- [ ] Run full suite → PASS.

### Task 3: CLI, skill, docs, version

**Files:** `ai_rubric/cli.py`, `skills/consult/SKILL.md`, `README.md`, `CHANGELOG.md`, `ai_rubric/__init__.py`; Tests `tests/test_cli.py`, `tests/test_skill.py`

- [ ] Tests: `--from agy` accepted; stand-in note names the model(s) that ran (host read from `run.json` on resume); skill body contains `--from agy`.
- [ ] Implement; `--from` help "claude (Claude Code), codex or agy (Antigravity)". Note text: `Note: a judge hit its usage limit; <model> was called in its place.` for each stand-in.
- [ ] Docs: host table row for Antigravity; CHANGELOG 1.1.0.

### Task 4: Installer

**Files:** Create `install/antigravity-plugin/plugin.json`, symlink `install/antigravity-plugin/skills/consult -> ../../../skills/consult`; Modify `install.sh`; Test `tests/test_install.py`

- [ ] Tests: install links `~/.gemini/config/plugins/ai-rubric -> $REPO/install/antigravity-plugin` and `…/skills/consult/SKILL.md` resolves; GEMINI.md block contains both "When judging" and "Second opinions"; uninstall removes the link.
- [ ] Implement: add link to `LINKS`; GEMINI.md upsert from a temp file = gemini-rules.md + blank line + claude-rule.md.
- [ ] Full suite → PASS; run real `./install.sh`; check Antigravity sees the skill.
