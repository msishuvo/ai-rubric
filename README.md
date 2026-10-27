# ai-rubric

Independent second opinions for judgment calls. From Claude Code or Codex, the
`consult` skill sends a neutral brief to the other two pinned models. Each
model reads the workspace itself, argues for and against the proposal without
knowing who wrote it, and gives a verdict.

## Judges

| Host you are in | Judges |
|---|---|
| Claude Code | Codex `gpt-6-astra` (medium) and Antigravity `gemini-4-argon-high` |
| Codex | Claude `claude-opus-5-5` (medium) and Antigravity `gemini-4-argon-high` |

The models are fixed in code (`ai_rubric/judges.py`). If a judge can't run,
it is reported as failed and nothing replaces it.

## Install, once per machine

    git clone git@github.com:msishuvo/ai-rubric.git
    cd ai-rubric && ./install.sh

The installer:

- links `skills/consult` into `~/.claude/skills/` and `~/.codex/skills/`
- links `bin/consult` into `~/.local/bin/`
- adds a marked rule block to `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`
  and `~/.gemini/GEMINI.md`
- allows `consult` in `~/.codex/rules/default.rules`
- reports which judge CLIs it found

Running it again changes nothing. It never edits text outside its own
`ai-rubric start/end` markers. Needs Python 3.11+, and `claude`, `codex` and
`agy`, each logged in.

## When it runs

The host tool decides. It runs `consult` when an independent opinion could
change the outcome: design, UI, architecture, product or pricing scope,
choosing between options, or reviewing a proposal. It does not run for
lookups, small edits or clear bugs.

- Force it: "consult", "council this" or `/consult`.
- Skip it: "no council".

## Running it by hand

    consult --from claude --brief brief.md [--add-dir ../other-folder]

Run it from the project folder. `--from` names the tool you are in. The
brief must not say who wrote the proposal or which way anyone leans; the
script refuses briefs that look like they do (exit 3). Pass
`--allow-flagged` only when the flagged words are the subject itself.

| Exit | Meaning |
|---|---|
| 0 | at least one verdict |
| 1 | both judges failed |
| 2 | usage, config or pre-run error |
| 3 | brief refused |

## Where results go

`~/.local/state/ai-rubric/consultations/<time>-<slug>/` holds `brief.md`,
`prompt.md`, one verdict file per judge, and `run.log`.

## Config (optional)

`~/.config/ai-rubric/config.toml`:

    timeout = 1200                 # seconds per judge
    save_root = "~/consultations"
    extra_dirs = ["~/shared-notes"] # always readable by judges
    pre_run = ["free-mem-check"]   # must exit 0 before judges start
    [cli]
    codex = "/custom/path/codex"

Model and effort keys are rejected.

## Uninstall

    ./install.sh --uninstall

Removes only its own links and marked blocks.

## Tests

    python3 -m unittest discover -s tests -t . -v

Standard library only.

## History

This repository used to hold the Rubric plugin. Its last version is tagged
`rubric-final`.
