# Rubric: design

**Status:** approved design, not yet implemented
**Date:** 2026-09-03
**Author:** msishuvo + Claude
**Next step:** implementation plan via `superpowers:writing-plans`

Rubric is a Claude Code plugin that carries a project's own standards into
every turn and holds work to them mechanically. One engine, shipped once per
device; one small config file per project, describing what that project counts
as evidence.

---

## 1. Why this exists

The Sortie project (`~/Documents/Apps/Sortie`) accumulated a working method
over several months: three questions asked before any factual claim, a table
of what each kind of check actually costs, a rule that platform questions are
researched rather than recalled, and a habit of ending a visual change in a
screenshot somebody looked at.

Two findings from that project drive this entire design.

**Finding one: the prose did not hold.** `docs/how-we-build-sortie.md` records
the "an exit code is not proof" rule being broken roughly an hour after it was
written down. A file read at session start is buried under a hundred thousand
tokens by the time the mistake happens. Separately, the 2026-09-02 audit found
that *every* convention violation in the tree broke a rule the project's
CLAUDE.md already stated, several of them in files whose own comments quoted
the rule.

**Finding two: the mechanisms did hold.** Three of them:

| Mechanism | Kind | What it does |
|---|---|---|
| `build_discipline.py` | `UserPromptSubmit` hook | injects the three questions into every prompt, not once at startup |
| `evidence_gate.py` | `Stop` hook | blocks a turn that changed code, claimed it works, and ran nothing |
| `check_invariants.py` | script | greps the conventions a grep can settle |

Rubric generalises the mechanisms, not the prose. A version of this kit that
shipped only a well-written rulebook would be shipping the half that is already
known to fail.

## 2. Scope

**In scope**

- A plugin installable from a git repo, carrying two hooks, one script, one
  setup skill and two presets.
- A per-project config file describing that project's evidence.
- Two dialects: `code` (evidence is that something ran) and `research`
  (evidence is that a source was actually opened or a number actually
  recomputed).
- A setup skill that works backwards from repositories that already exist.

**Out of scope**

- **Sortie is not migrated.** Its hooks work, they are tuned to it, and two of
  its eight invariants are real Python rather than regexes, so they would not
  survive the move. Sortie stays exactly as it is and remains the reference
  implementation and evidence base for the `code` dialect.
- Per-project Python invariants. The runner is designed so this seam can be
  opened later without breaking the contract, but it stays closed until a
  project actually needs it.
- Any config UI, auto-update mechanism, or telemetry.

## 3. Distribution

A single git repository, `claude-rubric`, containing one plugin named `rubric`.

Per device, once:

```
claude plugin marketplace add msishuvo/claude-rubric
claude plugin install rubric@claude-rubric
```

Both command forms verified against `claude plugin --help` and
`claude plugin marketplace add --help` on 2026-09-03. **Not yet checked:**
whether a private GitHub repository needs additional auth for
`marketplace add`. This is testable at first install; a public repository
containing nothing secret is an acceptable fallback.

After install, `git push` to the repo plus `claude plugin update rubric`
propagates a change to every device and every project.

Naming, fixed:

| Thing | Name |
|---|---|
| Repository and local folder | `claude-rubric` |
| Plugin | `rubric` |
| Setup skill, as invoked | `rubric:setup` |
| Per-project config | `.claude/rubric.json` |
| Per-device defaults | `~/.claude/rubric.json` |

## 4. Repository layout

```
claude-rubric/
  .claude-plugin/
    marketplace.json         # lets `marketplace add msishuvo/claude-rubric` resolve
    plugin.json              # name, version, description, repository
  hooks/
    hooks.json               # UserPromptSubmit + Stop, via ${CLAUDE_PLUGIN_ROOT}
    rubric_context.py        # UserPromptSubmit
    evidence_gate.py         # Stop
    rubric_config.py         # shared: load, merge, validate
  scripts/
    check_invariants.py      # generic runner
  skills/
    setup/
      SKILL.md               # the rubric:setup interview
  presets/
    code.json
    research.json
  tests/
    test_config.py
    test_context.py
    test_evidence_gate.py
    test_invariants.py
    fixtures/                # fabricated transcripts
  docs/
    superpowers/specs/       # this file
  README.md
```

## 5. The config contract

### 5.1 Resolution order

Later wins:

1. built-in defaults (in `rubric_config.py`)
2. the preset named by `dialect`
3. `~/.claude/rubric.json` (per-device: mainly `who` and `cannot_check`)
4. `<project>/.claude/rubric.json`

Objects deep-merge. Arrays replace wholesale, **except** that any array key may
be written with a trailing `+` to append to the inherited value instead:

```json
{ "evidence": { "commands+": ["make integration"] } }
```

This matters because the common edit is "the preset is right, plus one more
command", and forcing a full retype of the preset's list is how a config
silently loses a rule during an unrelated edit.

### 5.2 Behaviour with no config at all

The plugin's hooks fire in **every** project on a device where it is enabled,
including projects that have never heard of it. That case is defined, not
accidental:

- `rubric_context.py` injects the three questions **only**, with no name and no
  situation blocks.
- `evidence_gate.py` is **disabled entirely**. Without config it cannot know
  what evidence means in that repository, and a gate that guesses is a gate
  that gets switched off.
- `check_invariants.py` reports "no invariants configured" and exits 0.

This is what makes the "generic now, deepen later" promise real, and it means
`rubric:setup` never has to touch a project's `.claude/settings.json`. The
plugin brings its own hook wiring; the project file only supplies knowledge.
Setup is therefore additive by construction: it writes exactly one new file.

### 5.3 Fields

| Key | Type | Meaning |
|---|---|---|
| `dialect` | `"code"` \| `"research"` | which preset to inherit |
| `who` | string | the person's name, used in question 3 |
| `cannot_check` | string[] | the domains they have said they cannot verify |
| `work_files` | glob[] | what counts as "the work" being changed; unused when `gate.requires_work_change` is false |
| `evidence.commands` | regex[] | shell commands that actually exercise the project |
| `evidence.tools` | string[] | tool-name prefixes that count as evidence |
| `evidence.never_started` | regex[] | output proving a command did not do what it names |
| `claims` | regex[] | assistant text that asserts the work is correct |
| `disclaimers` | regex[] | the sanctioned way past the gate |
| `gate.enabled` | bool | default true once a config exists |
| `gate.requires_work_change` | bool | see 7.2 |
| `cost_table` | row[] | `{ claim, check, cost }`, quoted by the gate when it blocks |
| `situations` | block[] | `{ when: regex[], say: string }` |
| `invariants` | rule[] | see section 8 |

### 5.4 A minimal config

```json
{
  "dialect": "code",
  "who": "msishuvo",
  "cannot_check": ["Rust internals", "async runtime behaviour"]
}
```

### 5.5 A fuller one

```json
{
  "dialect": "code",
  "who": "msishuvo",
  "cannot_check": ["TypeScript type inference edge cases"],
  "work_files": ["src/**/*.ts", "src/**/*.tsx"],
  "evidence": {
    "commands+": ["npm run typecheck"],
    "never_started+": ["No test files found", "0 passing"]
  },
  "cost_table": [
    { "claim": "the tests pass", "check": "npm test, and read the count",   "cost": "~30s" },
    { "claim": "it builds",      "check": "npm run build, read final line", "cost": "~20s" },
    { "claim": "the page looks right", "check": "open it and look",         "cost": "~60s" }
  ],
  "situations": [
    { "when": ["\\breact\\b", "\\bhooks?\\b", "\\brender\\b"],
      "say": "React behaviour is researched, not recalled. Fetch the docs page." }
  ],
  "invariants": [
    { "name": "no-console-log",
      "files": "src/**/*.ts",
      "forbid": "console\\.log",
      "message": "logging goes through logger.ts",
      "rule_source": "CLAUDE.md > Conventions" }
  ]
}
```

## 6. Presets

### 6.1 `code`

A direct port of Sortie's, with the Swift and Xcode specifics lifted out and
left to the project file.

- `claims`: `fixed`, `verified`, `confirmed`, `resolved`, `passes`, `passing`,
  `now works`, `works now`, `is working`, `should work`, `no longer
  (breaks|fails|crashes)`, `that does it`.
  Bare `working` is deliberately excluded: "working directory", "working
  agreement" and "working on it" are all common and none is a claim.
- `disclaimers`: `i have not checked this`, `i have not (run|built|tested|
  verified)`, `not verified`, `unverified`, `did not build`.
- `evidence.commands`: detected per project; the preset ships only the
  universally safe ones (`make`, `npm test`, `pytest`, `cargo test`,
  `go test`) as candidates for setup to confirm.
- `never_started`: `BUILD FAILED`, `command not found`, `No such file`,
  `error:`, plus whatever setup adds.
- `gate.requires_work_change`: `true`.

### 6.2 `research`

The less proven of the two. See section 11.

- `claims`: `the (paper|study|report|data|source) (says|shows|found)`,
  `according to`, `research (shows|suggests)`, `\d+% of`, `studies (show|find)`,
  `it turns out that`, `the numbers say`.
- `evidence.tools`: `Read`, `WebFetch`, `WebSearch`, `Bash` (for a recomputation).
- `never_started`: `404`, `could not fetch`, `no results found`,
  `Traceback (most recent call last)`.
- `gate.requires_work_change`: `false`. In research a false claim need not be
  accompanied by an edit, so the gate keys on claim-without-source rather than
  on files changing. This is the single riskiest parameter in the design and is
  expected to need retuning against real sessions.

## 7. The hooks

### 7.1 `rubric_context.py` (UserPromptSubmit)

Always injects the core block, which is the only text in the whole kit that is
hardcoded rather than configured, because it is the one thing that is genuinely
universal:

```
Before any factual claim this turn:
  1. Checked, or recalled? If recalled and checkable in under two minutes, check it.
  2. What did I observe, versus what am I inferring?
  3. If I am wrong here, could <who> tell? They cannot check <cannot_check>. If no, slow down.
Anything unchecked ships with the words "I have not checked this".
```

Then appends any `situations` block whose `when` patterns match the prompt.
Matching is word-boundary throughout, so `classify` cannot fire a rule written
for `class`.

The `cost_table` is deliberately **not** injected here. It belongs to the gate
(7.2), which quotes the one relevant row at the moment a check was skipped.
Injecting the whole table every turn would be the wallpaper problem again.

The always-on block stays deliberately small. A hook that costs a paragraph a
turn becomes wallpaper, which is precisely how the prose it replaces stopped
working.

Never blocks. Any unexpected condition exits 0 with no output.

### 7.2 `evidence_gate.py` (Stop)

Blocks once per session when **all** of these hold:

1. this stop is not already a re-entry (`stop_hook_active`, plus a per-session
   marker file, because relying on a payload field never observed live is
   itself an unchecked claim);
2. `gate.enabled` and a project config exists;
3. some assistant **text** this turn matches `claims`;
4. that text matches no `disclaimers`;
5. if `gate.requires_work_change`, a `work_files` path was changed this turn,
   by an edit tool **or** by a shell command that writes (auto mode edits
   through Bash, so missing this would quietly retire the gate);
6. no `evidence.commands` ran and no `evidence.tools` were used, **or** one did
   and its own output matches `never_started`.

The conjunction is deliberately tight. Discussion, refactors reported honestly,
and answering a question all pass untouched. A gate that cries wolf gets
switched off, and then it protects nothing.

Excluded from consideration: thinking blocks (a claim the user never reads
cannot mislead them) and subagent output (`isSidechain`; another agent's build
is not this session's evidence).

The block message names the specific check to run, drawn from `cost_table`,
rather than scolding in the abstract.

**Fail open, always.** Every unexpected condition exits 0 and allows the stop.
A gate that breaks a session is worse than no gate; it gets removed within a
day and takes its protection with it.

## 8. `check_invariants.py`

A generic runner over declarative rules.

```json
{
  "name": "no-console-log",
  "files": "src/**/*.ts",
  "forbid": "console\\.log",
  "allow": "eslint-disable",
  "require": null,
  "skip_line_comments": ["//"],
  "message": "logging goes through logger.ts",
  "rule_source": "CLAUDE.md > Conventions"
}
```

`forbid` reports any matching line. `require` is its inverse and is
file-scoped: a matched file in which the pattern appears nowhere is reported
once, which is how a mandatory licence header or import is checked. `allow`
suppresses a `forbid` hit when it matches the same line. A rule sets `forbid`
or `require`, never both.

`rule_source` is **required**. This is the Sortie lesson made structural: every
violation that audit found broke a rule the project had already written down,
so a grep must name the prose it enforces. A check that cannot cite a rule is
policing something nobody agreed to.

Output is a triage table, not a verdict. **Exit 0 always.** A check that breaks
a commit gets deleted in annoyance and takes its protection with it. Some
flagged lines will be correct on reading; the runner reports and the human
decides.

The seam for per-project Python is documented in the runner but not wired: a
future version globs `.claude/rubric.d/*.py`. It stays closed until a project
earns it.

## 9. `rubric:setup`

Most target repositories already exist, so the skill reads before it asks.

**Step 1, detect.** Draft a config from evidence in the repo:

| Found | Infers |
|---|---|
| `package.json` `scripts.test` / `.build` | evidence commands |
| `pyproject.toml`, `pytest.ini`, `tox.ini` | `pytest` |
| `Cargo.toml` | `cargo test`, `cargo build` |
| `go.mod` | `go test ./...` |
| `Makefile` targets `test` / `build` | `make test` |
| existing `CLAUDE.md` / `AGENTS.md` | candidate invariants, and their `rule_source` |
| `git log --stat` over recent commits | which paths are actually the work |
| absence of any of the above | `research` dialect is the likely answer |

**Step 2, propose.** Show the drafted config and the reasoning. Not a blank
interview.

**Step 3, ask only what cannot be inferred.** Chiefly `cannot_check`, which
nothing in the repository knows. Then confirm the detected commands actually
run, by running one.

**Step 4, write additively.** Exactly one new file, `.claude/rubric.json`
(creating `.claude/` if the repository has none), shown as a diff first. Nothing else in the repository is modified. If a
`.claude/rubric.json` already exists it is merged into, never replaced.

**Step 5, prove it.** Run `check_invariants.py` once and show the output, so
the project's first experience of the kit is a real result rather than a claim
that it is installed.

## 10. Testing

Given what this kit is about, the verification strategy is not optional.

- **Unit tests, pure Python, no Claude Code required.** Fabricated transcript
  JSONL fixtures drive the gate through every one of its six conditions in both
  dialects, plus the loop guard, plus the fail-open path for malformed input.
  Config merging gets its own tests, including the `key+` append form.
- **`claude plugin validate . --strict`** for the manifests. Verified to exist
  on 2026-09-03.
- **One real end-to-end.** Install on an actual second project, make a
  deliberately unverified claim, and show the terminal output of the gate
  firing. No screenshot of a passing test suite substitutes for this.

The phrase "should work" does not appear in any completion report for this
project. The gate blocks that phrase for a reason.

## 11. Risks and unknowns, stated plainly

- **The `research` dialect is unproven.** The `code` dialect is a port of
  something demonstrably working in Sortie for months. The research one is
  reasoned from first principles and has never fired. Expect to retune
  `claims` and `gate.requires_work_change` against real sessions. It ships
  with the gate defaulting to enabled but is the first thing to disable if it
  proves noisy.
- **Private repository auth for `marketplace add` is unchecked.** Testable at
  first install.
- **Hooks only exist inside Claude Code.** Nothing here helps in a plain API
  session, another editor, or the web app. The kit is a harness feature, not a
  property of the work.
- **The Stop hook sees only the end of a turn.** It catches the reflex, not the
  reasoning. The written standards remain what actually binds; the mechanisms
  are a backstop for the moment of highest confidence, which is when the
  mistake happens.
- **A device-wide plugin means device-wide hooks.** Section 5.2 defines the
  no-config case precisely so this is harmless, but any change to that default
  affects every repository on the machine at once.

## 12. Relationship to Sortie

Sortie is untouched by this work and keeps its own hooks, its own
`check_invariants.py`, and its own eight checks. It remains the evidence base:
the `code` preset is a generalisation of what is running there, and
`docs/how-we-build-sortie.md` and `docs/working-agreement.md` are the source
documents for the core block.

If Rubric later proves itself on two or three other projects, migrating Sortie
becomes a separate decision with its own brainstorm, and would require the
per-project Python seam of section 8 to be opened first.
