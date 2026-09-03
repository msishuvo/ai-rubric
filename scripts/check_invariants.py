#!/usr/bin/env python3
"""Run a project's configured invariants.

    python3 scripts/check_invariants.py [project_dir]

Exit 0 always. This reports, it never blocks. A check that breaks a commit
gets deleted in annoyance and takes its protection with it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rubric import config as rubric_config  # noqa: E402
from rubric import invariants  # noqa: E402


def main(argv):
    root = argv[1] if len(argv) > 1 else os.getcwd()
    loaded, configured = rubric_config.load(root)
    if not configured:
        print("No .claude/rubric.json in %s, so no invariants are configured. "
              "Run /rubric:setup to add some." % root)
        return 0

    rules = loaded.get("invariants") or []
    if not rules:
        print("No invariants configured for this project.")
        return 0

    problems = invariants.validate(rules)
    findings = invariants.run(root, rules)
    print(invariants.report(findings, problems))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as error:  # noqa: BLE001
        print("check_invariants could not complete: %s" % error)
        sys.exit(0)
