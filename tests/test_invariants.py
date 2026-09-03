"""Tests for rubric.invariants."""

import os
import shutil
import tempfile
import unittest

from rubric import invariants


class Tree(object):
    """A throwaway directory with files in it."""

    def __init__(self, files):
        self.root = tempfile.mkdtemp()
        for name, body in files.items():
            path = os.path.join(self.root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def rule(**overrides):
    base = {"name": "no-console", "files": "src/**/*.ts",
            "forbid": r"console\.log", "message": "use logger.ts",
            "rule_source": "CLAUDE.md > Conventions"}
    base.update(overrides)
    return base


class ValidateTests(unittest.TestCase):
    def test_a_rule_without_rule_source_is_rejected(self):
        broken = rule()
        del broken["rule_source"]
        problems = invariants.validate([broken])
        self.assertTrue(any("rule_source" in p for p in problems))

    def test_a_rule_with_neither_forbid_nor_require_is_rejected(self):
        broken = rule()
        del broken["forbid"]
        self.assertTrue(any("forbid" in p for p in invariants.validate([broken])))

    def test_a_rule_with_both_forbid_and_require_is_rejected(self):
        problems = invariants.validate([rule(require="x")])
        self.assertTrue(any("both" in p for p in problems))

    def test_an_invalid_regex_is_reported_rather_than_raising(self):
        self.assertTrue(any("regex" in p for p in invariants.validate([rule(forbid="(")])))

    def test_a_well_formed_rule_has_no_problems(self):
        self.assertEqual(invariants.validate([rule()]), [])


class ForbidTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "tree"):
            self.tree.cleanup()

    def test_a_forbidden_pattern_is_reported_with_its_line(self):
        self.tree = Tree({"src/a.ts": "const x = 1;\nconsole.log(x);\n"})
        findings = invariants.run(self.tree.root, [rule()])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 2)
        self.assertEqual(findings[0].rule, "no-console")

    def test_a_finding_carries_the_rule_source_forward(self):
        self.tree = Tree({"src/a.ts": "console.log(1);\n"})
        findings = invariants.run(self.tree.root, [rule()])
        self.assertEqual(findings[0].rule_source, "CLAUDE.md > Conventions")

    def test_a_file_outside_the_glob_is_not_looked_at(self):
        self.tree = Tree({"docs/a.ts": "console.log(1);\n"})
        self.assertEqual(invariants.run(self.tree.root, [rule()]), [])

    def test_allow_suppresses_a_hit_on_the_same_line(self):
        self.tree = Tree({"src/a.ts": "console.log(1); // eslint-disable\n"})
        findings = invariants.run(self.tree.root, [rule(allow="eslint-disable")])
        self.assertEqual(findings, [])

    def test_allow_does_not_suppress_a_hit_on_another_line(self):
        self.tree = Tree({"src/a.ts": "// eslint-disable\nconsole.log(1);\n"})
        findings = invariants.run(self.tree.root, [rule(allow="eslint-disable")])
        self.assertEqual(len(findings), 1)

    def test_whole_line_comments_are_skipped_when_configured(self):
        self.tree = Tree({"src/a.ts": "// console.log(1);\n"})
        findings = invariants.run(
            self.tree.root, [rule(skip_line_comments=["//"])])
        self.assertEqual(findings, [])

    def test_a_vendored_directory_is_never_walked(self):
        self.tree = Tree({"node_modules/src/a.ts": "console.log(1);\n"})
        self.assertEqual(invariants.run(self.tree.root, [rule(files="**/*.ts")]), [])


class RequireTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "tree"):
            self.tree.cleanup()

    def header_rule(self):
        return {"name": "licence-header", "files": "src/**/*.ts",
                "require": r"^// Copyright", "message": "every file carries the header",
                "rule_source": "CLAUDE.md > Legal"}

    def test_a_file_missing_the_required_pattern_is_reported_once(self):
        self.tree = Tree({"src/a.ts": "const x = 1;\nconst y = 2;\n"})
        findings = invariants.run(self.tree.root, [self.header_rule()])
        self.assertEqual(len(findings), 1)
        self.assertIsNone(findings[0].line)

    def test_a_file_carrying_it_is_not_reported(self):
        self.tree = Tree({"src/a.ts": "// Copyright 2026\nconst x = 1;\n"})
        self.assertEqual(invariants.run(self.tree.root, [self.header_rule()]), [])


class ReportTests(unittest.TestCase):
    def test_no_findings_says_so_plainly(self):
        text = invariants.report([], [])
        self.assertIn("No findings", text)

    def test_a_finding_prints_path_line_and_rule(self):
        finding = invariants.Finding("no-console", "src/a.ts", 2, "console.log(x);",
                                     "use logger.ts", "CLAUDE.md > Conventions")
        text = invariants.report([finding], [])
        self.assertIn("src/a.ts:2", text)
        self.assertIn("no-console", text)
        self.assertIn("CLAUDE.md > Conventions", text)

    def test_rule_problems_are_shown_above_findings(self):
        text = invariants.report([], ["rule 'x' has no rule_source"])
        self.assertIn("rule_source", text)

    def test_the_report_contains_no_em_dash(self):
        finding = invariants.Finding("r", "a.ts", 1, "x", "m", "s")
        self.assertNotIn("—", invariants.report([finding], ["p"]))


if __name__ == "__main__":
    unittest.main()
