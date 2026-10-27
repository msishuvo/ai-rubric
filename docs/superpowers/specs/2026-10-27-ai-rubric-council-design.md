# ai-rubric: independent judgment from three models

Date: 2026-10-27. Replaces the Rubric plugin (last version tagged `rubric-final`).

## Why

The owner works in two tools, Claude Code and Codex, and pays for ChatGPT Plus
and Google AI Pro. On judgment calls (design, architecture, product scope,
choosing between options) one model tends to agree with whoever is talking to
it. The trigger case: the owner doubted a plan, asked a second model, and the
second model agreed, which proved nothing, because it would probably have
agreed with the opposite view too.

The goal is argument on the merits from judges who cannot see whose idea it
is or which way the owner leans, and who read the workspace themselves.

## Goals

- From either host tool, get verdicts from the other two judges on a proposal.
- Judges are pinned. Never substitute a different model or effort level:

  | Judge | Model | Effort | Command shape |
  |---|---|---|---|
  | Claude | `claude-opus-5-5` | medium | `claude -p --model claude-opus-5-5 --effort medium` |
  | Codex | `gpt-6-astra` | medium | `codex exec -m gpt-6-astra -c model_reasoning_effort="medium" -s read-only` |
  | Antigravity | `gemini-4-argon-high` | (in the model id) | `agy -p --model gemini-4-argon-high` |

  Host Claude → judges Codex + Antigravity. Host Codex → judges Claude +
  Antigravity. Antigravity is never a host.
- Works in any project on any machine (this Mac, the owner's remote server).
  Nothing is project-specific.
- Judges read the whole workspace themselves, read-only.
- Disagreement reaches the owner intact; nothing is averaged away.

## Non-goals

- Not for straightforward work: factual lookups, explaining a file, small
  edits, bugs with a clear cause, running commands.
- Not code delegation. Judges never edit files.
- No Antigravity host mode, no UI, no server.

## Anti-goals (failure even if it runs)

- A judge learns who wrote the proposal or what the owner prefers.
- A judge reviews a summary instead of reading the files.
- A missing model is silently replaced by another one.
- The host reports "the judges agree" when they did not, or folds a dissent
  into a blended answer.
- It fires on every question and becomes noise the owner switches off.

## When it runs

The host decides, guided by the skill description and one rule block in its
global instructions:

- Run when an independent second opinion could change the outcome: design and
  UI choices, architecture, product or pricing scope, comparing options,
  reviewing a plan or proposal (the host's own, the owner's, or another
  tool's), and when the owner asks "is this good enough?".
- Do not run for straightforward questions (see non-goals).
- Owner overrides: "consult" / "council this" / `/consult` forces a run;
  "no council" skips it.

## The brief (what judges receive)

Written by the host to a file, then passed to each judge. Contents:

1. The question or decision, stated neutrally.
2. The proposal under review, with its reasoning, labelled only "the
   proposal". No author.
3. Hard constraints and facts the owner stated in chat that are not in any
   file (deadlines, budgets, audiences, requirements). Stated as facts, not
   as anyone's opinion.
4. Files and folders the proposal relied on, as starting points only.
5. The workspace roots the judge may read.

Excluded on purpose: who wrote the proposal; the owner's feelings, doubts or
leanings about it ("I feel this isn't valuable"); what any other model said.
If the owner's doubt is itself the question, the host rewrites it neutrally
("Is this plan valuable enough to ship? Argue both ways.").

The skill tells the host to check its brief against this list before sending.

## What each judge does

Fixed judge instructions, prepended to the brief by the script:

- Read the workspace yourself; treat the brief's file list as a start, not a
  limit. Do not edit anything.
- Write the strongest case for the proposal, then the strongest case against
  it, each with evidence (file paths, lines, sources).
- Then a verdict: keep / change / drop, what is missing, and confidence.
- Say what you could not check.

Verdict format (markdown, fixed headings): Case for, Case against, Verdict,
Missing, Evidence, Not checked.

## What the owner sees

The host reads both verdicts and reports, in this order:

1. Where the judges agree and disagree with the proposal, one line each.
2. The strongest argument on each side, with the judge named.
3. What the host now thinks, and specifically what it changed its mind on.
   If it keeps its position against a judge, it says why.
4. Path to the saved consultation folder.

Unresolved disagreement is stated as unresolved.

## Parts

- `skills/consult/SKILL.md`: one file, read by both Claude Code and Codex.
  Trigger description, brief checklist, how to call the script, reporting
  format.
- `bin/consult`: Python 3, standard library only (runs on the Mac and the
  server without installs). Usage:
  `consult --from claude|codex --brief FILE [--add-dir DIR ...]`.
  - Picks the two judges for the host. `--from` is required; the skill tells
    each host which value is its own.
  - Finds each CLI: config path, then `PATH`, then known locations (on this
    Mac, Codex is inside `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`).
  - Runs both judges in parallel from the current directory, with every
    `--add-dir` passed through in each CLI's own form, read-only.
  - Timeout per judge (default 20 minutes, configurable).
  - If a judge's CLI or model is missing or the run fails, report that judge
    as failed with its error. Never substitute. Exit non-zero only if both
    fail.
  - Optional pre-run command from config (for the server's memory check).
- Saved consultations: `~/.local/state/ai-rubric/consultations/<timestamp>-<slug>/`
  holding `brief.md`, one verdict file per judge, and a run log. Location
  configurable; outside the project so it never dirties a repo.
- Config: `~/.config/ai-rubric/config.toml`, optional. CLI paths, extra
  workspace roots, timeout, log location, pre-run command. Models are not
  configurable.
- `install.sh`, idempotent, with `--uninstall`:
  - Symlinks `skills/consult` into `~/.claude/skills/consult` and
    `~/.codex/skills/consult`; links `bin/consult` into `~/.local/bin`.
  - Adds a marked rule block (`<!-- ai-rubric start/end -->`) to
    `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`. Never rewrites anything
    outside the markers.
  - Adds judge rules to `~/.gemini/GEMINI.md` (currently empty on the Mac):
    read before asserting, never invent, say what was not checked.
  - Adds a Codex rule allowing `consult` to run outside the sandbox, since
    the Claude and Antigravity judges need network access. Scoped to this
    one command.
- Tests: standard-library `unittest` for judge selection, CLI discovery,
  command building, brief assembly, failure handling, and the install
  markers (against a temporary home folder).
- README: what it is, install, when it runs, how to force or skip, where
  results go.

The old Rubric files (hooks, presets, rubric package, setup skill, plugin
manifest, its specs and plans) are removed. History stays at `rubric-final`.

## Decided by the owner

- Hosts are Claude Code and Codex; Antigravity is a judge in both cases.
- Models and efforts as in the table, Astra specifically.
- Runs only when judgment is needed, not on straightforward questions.
- Must work in any project and on the remote server.
- Repo repurposed and renamed `ai-rubric`; Rubric plugin uninstalled.

## Calls made by Claude (check these)

- Skill name `consult`; repo `ai-rubric`.
- Python standard library for the script, as the old repo was.
- Default timeout 20 minutes.
- Consultations saved outside the project by default.
- Judges get the same brief; the host does not see one verdict before the
  other judge runs.
- Codex's `~/AGENTS.md` copy in the home folder is left alone; only
  `~/.codex/AGENTS.md` gets the rule block.

## Left to the builder

- Exact read-only flags for `claude` and `agy` (verify against `--help` and
  a real run; `agy --mode plan` and `claude --permission-mode plan` are
  candidates).
- How each CLI accepts extra directories and a prompt from a file or stdin.
- The exact Codex rule-file syntax for the sandbox allowance.
- That Codex loads skills from `~/.codex/skills/` (the folder exists, empty,
  on the Mac); if not, use whatever skill location this Codex version reads.
- Which CLIs and logins exist on the remote server; install must report a
  missing one, not fail silently.

## Done means

- A real consultation from Claude Code on this Mac returns Codex and
  Antigravity verdicts in the fixed format.
- A real consultation from Codex on this Mac returns Claude and Antigravity
  verdicts.
- The same from the remote server.
- A missing CLI produces a clear failed-judge report, not a substitute.
- Unit tests pass.
