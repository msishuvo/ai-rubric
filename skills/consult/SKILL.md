---
name: consult
description: Get independent, blind, two-sided verdicts from two other AI models (pinned Claude Opus 5.5, GPT-6 Astra, Gemini 4 Argon) on a proposal. Use when a second opinion could change the outcome - design or UI choices, architecture, product or pricing scope, choosing between options, reviewing a plan or proposal from anyone (yourself, the user, another tool), or the user asks "is this good enough?". Also when the user says "consult", "council this" or /consult. Do NOT use for factual lookups, explaining code, small edits, bugs with a clear cause, running commands, or when the user says "no council".
---

# consult

Two other models judge a proposal without knowing who wrote it or which way
anyone leans. They read the workspace themselves. You then report where they
agree and disagree, and what you changed your mind on.

The judges and models are fixed by the `consult` script. Never pick, swap or
add a model yourself.

## 1. Know which host you are

- In Claude Code, use `--from claude`. Your judges are Codex and Antigravity.
- In Codex, use `--from codex`. Your judges are Claude and Antigravity.

## 2. Write a neutral brief

Write the brief to a temporary file. It contains:

1. The question or decision, stated neutrally.
2. The proposal under review, with its reasoning, called only "the proposal".
3. Hard constraints and facts the user stated in chat that are in no file
   (deadlines, budgets, audiences, requirements), stated as facts.
4. Files and folders the proposal relied on, as starting points only.

Leave out, on purpose:

- who wrote the proposal (you, the user, another tool);
- the user's feelings, doubts or which way they lean ("I feel this isn't
  valuable enough");
- what any other model said about it.

If the user's doubt is itself the question, rewrite it neutrally: "Is this plan
valuable enough to ship? Argue both ways." Check the brief against this list
before sending it.

## 3. Run it

```
consult --from <claude|codex> --brief /path/to/brief.md [--add-dir DIR ...]
```

- Run from the project folder. Add `--add-dir` for every other workspace folder
  that bears on the question; judges may read all of them.
- It runs both judges in parallel and can take up to 20 minutes. Run it in the
  background or with a long timeout; do not poll it in a tight loop.
- In Codex, the command has to run outside the sandbox (judges need the
  network). The installer adds an allow rule for `consult`.
- If running `consult` is refused or blocked by an approval policy or reviewer,
  stop and tell the user it was blocked and why; they must approve it or change
  their policy. Do not retry inside the sandbox (the judges would have no
  network) and do not work around the block.

Exit codes: `0` at least one verdict, `1` both judges failed, `2` usage or
config error, `3` the brief was refused.

On exit `3` the script found words that may reveal authorship or leaning.
Rewrite the brief. Use `--allow-flagged` only when the flagged words are the
subject itself (for example, the question is about a module named "codex").

## 4. Report back

In this order:

1. Where the judges agree and disagree with the proposal, one line each.
2. The strongest argument on each side, naming which judge made it.
3. What you now think, and specifically what you changed your mind on. If you
   keep your position against a judge, say why.
4. The `Saved:` folder path the script printed.

State unresolved disagreement as unresolved. Never claim the judges agree when
the verdicts do not show it, and never blend a dissent into a consensus.

## 5. If a judge failed

Say which judge failed and the error the script printed (missing CLI, timeout,
not logged in, empty verdict). Report the verdict you did get.
Never run a substitute model to fill the gap.
