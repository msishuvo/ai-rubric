"""Tests for rubric.globs.

`fnmatch` is not path-aware and pathlib's `match` does not handle `**` the
way a .gitignore-shaped pattern implies, so the kit translates globs itself.
"""

import unittest

from rubric import globs


class MatchTests(unittest.TestCase):
    def test_a_plain_star_does_not_cross_a_separator(self):
        self.assertTrue(globs.matches("src/a.ts", "src/*.ts"))
        self.assertFalse(globs.matches("src/deep/a.ts", "src/*.ts"))

    def test_double_star_crosses_separators(self):
        self.assertTrue(globs.matches("src/deep/nested/a.ts", "src/**/*.ts"))

    def test_double_star_also_matches_zero_directories(self):
        self.assertTrue(globs.matches("src/a.ts", "src/**/*.ts"))

    def test_a_leading_double_star_matches_anywhere(self):
        self.assertTrue(globs.matches("a/b/c/x.py", "**/*.py"))
        self.assertTrue(globs.matches("x.py", "**/*.py"))

    def test_an_absolute_path_matches_a_relative_pattern_by_suffix(self):
        self.assertTrue(globs.matches("/home/me/proj/src/a.ts", "src/**/*.ts"))

    def test_a_question_mark_matches_one_non_separator_character(self):
        self.assertTrue(globs.matches("a1.ts", "a?.ts"))
        self.assertFalse(globs.matches("a/1.ts", "a?1.ts"))

    def test_a_dot_in_the_pattern_is_literal(self):
        self.assertFalse(globs.matches("srcXa/ts", "src/*.ts"))

    def test_matches_any_is_true_when_one_pattern_matches(self):
        self.assertTrue(globs.matches_any("src/a.ts", ["docs/*.md", "src/*.ts"]))

    def test_matches_any_of_nothing_is_false(self):
        self.assertFalse(globs.matches_any("src/a.ts", []))

    def test_a_non_string_pattern_does_not_raise(self):
        self.assertFalse(globs.matches("a.ts", ["not", "a", "string"]))


class AnchoredMatchTests(unittest.TestCase):
    def test_anchored_matches_the_rooted_path(self):
        self.assertTrue(globs.matches("src/a.ts", "src/**/*.ts", anchored=True))

    def test_anchored_does_not_match_a_longer_path_by_suffix(self):
        self.assertFalse(globs.matches("vendor/src/a.ts", "src/**/*.ts", anchored=True))

    def test_unanchored_default_is_unchanged(self):
        self.assertTrue(globs.matches("vendor/src/a.ts", "src/**/*.ts"))
        self.assertTrue(globs.matches("vendor/src/a.ts", "src/**/*.ts", anchored=False))


if __name__ == "__main__":
    unittest.main()
