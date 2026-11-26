# Antigravity as a consult host — design

## Intent

Run `consult` from inside Antigravity the same way as from Claude Code or Codex.
In Antigravity, the judges are the two non-Gemini models: Claude Opus 5.5 and
GPT-6.2 Astra, via the `claude` and `codex` CLIs exactly as today. If one hits
its usage limit, Gemini fills that slot so there are still two verdicts.

## Goals

- `consult --from agy` runs Claude (`claude-opus-5-5`, high) and Codex
  (`gpt-6.2-astra`, high) in parallel.
- Stand-in only on a usage limit (unchanged rule). Any other failure (missing
  CLI, not signed in, timeout) is reported as failed, as today.
- Stand-in model for an Antigravity host: the first limited slot gets Gemini 4
  Carbon (`gemini-4-carbon-high`, the usual Gemini judge); if the other slot
  is also limited, it gets Gemini 4 Neon (`gemini-4-neon-high`), so the two
  verdicts still come from different models.
- `consult --resume` works for agy-hosted runs, including stand-ins.
- The installer makes the skill and the "use consult" rule available in
  Antigravity.

## Non-goals

- No change for the Claude and Codex hosts (Codex/Claude + Carbon, Neon stands in).
- Models stay pinned in code; no config keys.
- Using Antigravity's own built-in Claude models instead of the `claude` CLI.

## Approaches considered

1. **Add `agy` to `HOSTS`; per-host stand-in list (picked).** Small change in
   `judges.py` and `run.py`; reuses every existing judge command.
2. Run Opus through `agy --model claude-opus-5-5-high`. Rejected: GPT is not
   available there, and it would differ from how Opus judges elsewhere.
3. Fixed stand-in per slot (Carbon for Claude, Neon for Codex). Simpler but a
   lone GPT limit would get Neon instead of the usual Carbon. Rejected.

## How

- `judges.py`: `HOSTS = ("claude", "codex", "agy")`; `judges_for("agy")` returns
  `[claude, codex]`; `stand_ins_for(host)` returns `[neon]` for claude/codex
  and `[carbon, neon]` for agy.
- `run.py`: when a slot hits its usage limit, it claims the first stand-in not
  already used in this run (under a lock; on resume, stand-ins already held in
  `run.json` count as used). Stale-export cleanup covers every stand-in name.
- `cli.py`: `--from` accepts `agy`; the stand-in note names the model that ran.
- Install: link `install/antigravity-plugin/` to
  `~/.gemini/config/plugins/ai-rubric/` (a `plugin.json` and `skills/consult`
  pointing at the repo skill); add the "Second opinions" rule to the existing
  marked block in `~/.gemini/GEMINI.md` alongside the judging rules.
  Uninstall removes both.
- Skill and README: document the Antigravity host and its stand-in rule.

## Known side effect

With the rule in GEMINI.md, the headless Gemini judge also sees "use consult".
It cannot run it (plan mode plus the read-only allow list), the same as the
Claude judge today.

## Left to the builder

Exact wording of skill/README text; test layout following existing tests.
