# Rubric

Carries a project's own standards into every turn and holds work to them.

Install, once per device:

    claude plugin marketplace add msishuvo/claude-rubric
    claude plugin install rubric@claude-rubric

Then, once per project:

    /rubric:setup

A project with no `.claude/rubric.json` gets the three verification
questions and nothing else. The gate stays off until a project has told it
what evidence means there.

Design: `docs/superpowers/specs/2026-09-03-rubric-design.md`
