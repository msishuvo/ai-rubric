# Rubric

Carries a project's own standards into every turn and holds work to them.

Three mechanisms, because prose alone does not hold. The project this grew
out of recorded its own "an exit code is not proof" rule being broken about
an hour after it was written down.

| Mechanism | When it runs | What it does |
|---|---|---|
| `rubric_context.py` | every prompt | asks three verification questions, plus any situation blocks the prompt matches |
| `evidence_gate.py` | end of a turn | blocks once when work changed, a completion claim was made, and nothing ran |
| `check_invariants.py` | on demand | greps the conventions a grep can settle, and reports rather than blocks |

## Install, once per device

    claude plugin marketplace add msishuvo/claude-rubric
    claude plugin install rubric@claude-rubric

## Set up, once per project

    /rubric:setup

## What happens in a project with no config

The three questions, and nothing else. The gate stays off and the invariant
checker reports that none are configured. A gate that guesses what evidence
means in a repository it has never been told about is a gate that gets
switched off, and then it protects nothing.

## Configuration

`.claude/rubric.json`. A dialect names a preset; every other key overrides
it. An array key ending in `+` appends to the inherited value instead of
replacing it.

    {
      "dialect": "code",
      "who": "msishuvo",
      "cannot_check": ["Rust internals"],
      "work_files": ["src/**/*.rs"],
      "evidence": { "commands+": ["cargo clippy"] }
    }

Device-wide defaults, mainly `who` and `cannot_check`, go in
`~/.claude/rubric.json`. A device-level file alone does not enable the
gate; that takes a project file.

Full field reference: `docs/superpowers/specs/2026-09-03-rubric-design.md`.

## The escape hatch

The gate is not asking for a build every time. Writing "I have not checked
this" in the sentence that makes the claim passes it, because the point is
that the person reading knows which sentences are load bearing.

## Running the tests

    python3 -m unittest discover -s tests -t . -v

Standard library only. No pip, no venv.

## Known limits

- The `research` dialect is the less proven half. Retune `claims` and
  `gate.requires_work_change` against real sessions.
- Hooks exist only inside Claude Code. Nothing here helps in a plain API
  session or another editor.
- The Stop hook sees only the end of a turn, so it catches the reflex and
  not the reasoning. The written standards are still what binds.
