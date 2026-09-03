---
name: setup
description: Use when adding Rubric to a project, or when the user asks to configure project standards, set up the evidence gate, add invariants, or says "rubric setup". Reads the repository first and proposes a config rather than running a blank interview.
---

# Setting up Rubric for a project

Write exactly one new file, `.claude/rubric.json`. Nothing else in the
repository is modified. The plugin brings its own hook wiring, so there is
no `settings.json` to edit.

## The rule that governs this whole skill

Read before you ask. Most repositories already answer most of these
questions, and an interview that asks what the repository could have told
you wastes the one thing the person has that you do not: their judgement
about what they cannot check.

## Step 1: Detect

Gather all of this before saying anything:

| Look at | Infer |
|---|---|
| `package.json` `scripts.test` / `scripts.build` | evidence commands |
| `pyproject.toml`, `pytest.ini`, `tox.ini` | `pytest` |
| `Cargo.toml` | `cargo test`, `cargo build` |
| `go.mod` | `go test ./...` |
| `Makefile` targets named `test` or `build` | `make test` |
| existing `CLAUDE.md` or `AGENTS.md` | candidate invariants, and the `rule_source` for each |
| `git log --stat -20` | which paths are actually the work |
| none of the above, and mostly prose files | the `research` dialect |

## Step 2: Propose

Show the drafted config and say where each part came from. Say plainly
which parts are guesses.

## Step 3: Ask only what the repository cannot tell you

One question at a time.

1. **`cannot_check`** is the important one, and nothing in the repository
   knows it. Ask: "Which parts of this could you not check yourself if I
   got them wrong?" Their answer goes in verbatim. This is what makes the
   third verification question answerable rather than rhetorical.
2. **`who`**, unless `~/.claude/rubric.json` already sets it.
3. Confirm the detected commands. Do not ask whether they work. Run one
   and show the output.

## Step 4: The cost table

Ask what each kind of claim actually costs to check here, and write a row per
kind: `{ "claim": ..., "check": ..., "cost": ... }`. Time the commands rather
than estimating them.

This is not decoration. The gate quotes these rows when it blocks, so a project
with no cost table gets a block message that names no way forward. It also
exists so that "verifying would take too long" cannot be said without looking
at a number somebody measured.

## Step 5: Invariants, if the repository has written rules

For each convention stated in the project's own CLAUDE.md that a grep
could settle, propose a rule. Every rule needs `rule_source` naming where
that convention is written. If a proposed check cannot cite a written
rule, do not add it. Propose no more than five to begin with; a checker
that fires forty times on its first run gets deleted.

## Step 6: Write

Show the file as a diff first. Create `.claude/` if the repository has
none. If `.claude/rubric.json` already exists, merge into it and never
replace it.

## Step 7: Prove it

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_invariants.py"` and show
the real output. The project's first experience of the kit is a result,
not a claim that it is installed.

Then say plainly what is now in force and what is not: the gate blocks a
completion claim only when a work file changed and nothing ran, and it
blocks once per session.
