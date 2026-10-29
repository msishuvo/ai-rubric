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
- pre-approves a few read-only shell commands (`ls`, `cat`, `head`, `tail`,
  `wc`, `grep`, `stat`, `du`, `pwd`) in Antigravity's global
  `~/.gemini/antigravity-cli/settings.json`. Headless Antigravity cannot ask
  for permission, and without these the Antigravity judge stops with no
  answer. They apply to all your Antigravity sessions.
- reports which judge CLIs it found

It checks Python and the existing markers first and changes nothing if either
is wrong. Running it again changes nothing. In the markdown and rules files it
only edits text between its own `ai-rubric start/end` markers; in
Antigravity's settings it adds only its own entries and removes only those.
Needs Python 3.11+ as `python3`, and `claude`, `codex` and `agy`, each logged
in.

## When it runs

The host tool decides. It runs `consult` when an independent opinion could
change the outcome: design, UI, architecture, product or pricing scope,
choosing between options, or reviewing a proposal. It does not run for
lookups, small edits or clear bugs.

- Force it: "consult", "council this" or `/consult`.
- Skip it: "no council".

In Codex, `consult` has to run outside the sandbox because the judges need
the network. If your Codex approval settings block it, Codex will tell you;
approve the run, or change the policy yourself.

## Running it by hand

    consult --from claude --brief brief.md [--add-dir ../other-folder]

Run it from the project folder. `--from` names the tool you are in. The
brief must not say who wrote the proposal or which way anyone leans; the
script refuses briefs that look like they do (exit 3). Pass
`--allow-flagged` only when the flagged words are the subject itself.

### Recovering an expired Claude sign-in

When Claude reports an expired login, `consult` keeps the other judge's verdict
and prints recovery commands. In an interactive terminal, use the printed saved
run directory:

    consult --resume '/path/to/saved/run' --login

This starts `claude auth login --claudeai` using the configured/discovered Claude
CLI. Complete the browser sign-in yourself. The command checks that subscription
authentication is active, then retries only the failed judges once. It never
substitutes a model or falls back to API billing. Successful verdict files stay
untouched, and previous failure messages remain in `run.log`.

Alternatively, sign in yourself with `claude auth login --claudeai`, then run:

    consult --resume '/path/to/saved/run'

Plain `--resume` also retries other judge failures. It uses the original saved
prompt, working directory and extra folders; omit `--from`, `--brief` and
`--add-dir`. If you used a custom `--config`, the printed recovery commands keep
that argument. Login only starts with explicit `--login` and interactive input
and output; background runs print instructions instead of opening a browser.

The judges read the live workspace. If files changed since the original run,
start a fresh consultation for comparable verdicts. A partial result is labeled
`PARTIAL`; the existing exit code stays 0 when at least one judge succeeded.
Runs created before this feature have no `run.json` and need a fresh consultation.
If a process was forcibly killed, remove its `.run.lock` only after confirming
that the consultation is no longer running.

| Exit | Meaning |
|---|---|
| 0 | at least one verdict |
| 1 | both judges failed |
| 2 | usage, config or pre-run error |
| 3 | brief refused |

## Where results go

`~/.local/state/ai-rubric/consultations/<time>-<slug>/` holds `brief.md`,
`prompt.md`, one verdict file per judge, `run.log`, and the `run.json` recovery
manifest. Results are checkpointed as each judge finishes.

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
