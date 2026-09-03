"""Tests for rubric.context."""

import unittest

from rubric import config, context


def cfg(**overrides):
    base = dict(config.DEFAULTS)
    base["evidence"] = dict(config.DEFAULTS["evidence"])
    base["gate"] = dict(config.DEFAULTS["gate"])
    base.update(overrides)
    return base


class CoreBlockTests(unittest.TestCase):
    def test_all_three_questions_are_present(self):
        block = context.core_block(cfg())
        self.assertIn("Checked, or recalled?", block)
        self.assertIn("observe, versus what am I inferring", block)
        self.assertIn("could", block)

    def test_the_escape_hatch_is_stated_verbatim(self):
        self.assertIn('"I have not checked this"', context.core_block(cfg()))

    def test_a_name_is_used_when_configured(self):
        self.assertIn("msishuvo", context.core_block(cfg(who="msishuvo")))

    def test_it_falls_back_to_the_user_when_no_name_is_configured(self):
        block = context.core_block(cfg())
        self.assertIn("the user", block)
        self.assertNotIn("None", block)

    def test_cannot_check_domains_are_named(self):
        block = context.core_block(cfg(who="msishuvo", cannot_check=["Rust internals"]))
        self.assertIn("Rust internals", block)

    def test_no_cannot_check_leaves_no_dangling_sentence(self):
        self.assertNotIn("They cannot check", context.core_block(cfg()))

    def test_the_block_contains_no_em_or_en_dashes(self):
        block = context.core_block(cfg(who="msishuvo", cannot_check=["a", "b"]))
        for glyph in ("—", "–", " - "):
            self.assertNotIn(glyph, block)


class SituationTests(unittest.TestCase):
    def setUp(self):
        self.config = cfg(situations=[
            {"when": [r"\breact\b"], "say": "React behaviour is researched, not recalled."},
            {"when": [r"\bscreenshot\b"], "say": "This ends in a picture somebody looked at."},
        ])

    def test_a_matching_situation_is_appended(self):
        blocks = context.situation_blocks(self.config, "why does react rerender here")
        self.assertEqual(blocks, ["React behaviour is researched, not recalled."])

    def test_a_non_matching_prompt_gets_nothing(self):
        self.assertEqual(context.situation_blocks(self.config, "rename this variable"), [])

    def test_matching_is_word_bounded(self):
        self.assertEqual(context.situation_blocks(self.config, "reactivity is fine"), [])

    def test_several_situations_can_fire_at_once(self):
        blocks = context.situation_blocks(self.config, "react screenshot please")
        self.assertEqual(len(blocks), 2)

    def test_a_situation_fires_only_once_even_with_two_matching_patterns(self):
        config_two = cfg(situations=[{"when": [r"\ba\b", r"\bb\b"], "say": "once"}])
        self.assertEqual(context.situation_blocks(config_two, "a b"), ["once"])

    def test_an_invalid_regex_is_skipped_rather_than_raising(self):
        broken = cfg(situations=[{"when": ["("], "say": "never"}])
        self.assertEqual(context.situation_blocks(broken, "anything"), [])

    def test_a_situation_with_no_say_is_ignored(self):
        empty = cfg(situations=[{"when": [r"\ba\b"]}])
        self.assertEqual(context.situation_blocks(empty, "a"), [])

    def test_the_cost_table_is_not_injected(self):
        with_table = cfg(cost_table=[{"claim": "the tests pass",
                                      "check": "npm test", "cost": "~30s"}])
        self.assertNotIn("npm test", context.build(with_table, "anything"))


class WordBoundarySafetyTests(unittest.TestCase):
    """A pattern with no explicit \\b still cannot fire on a mere substring.

    The spec states matching is word-boundary throughout, but a pattern
    written without \\b (a real user authoring their own situations,
    unaware they need it) previously matched anywhere in the prompt.
    """

    def test_a_pattern_with_no_explicit_boundary_does_not_fire_on_a_substring(self):
        config_no_boundary = cfg(situations=[
            {"when": ["class"], "say": "SITUATION"}])
        self.assertEqual(
            context.situation_blocks(config_no_boundary, "classify the rows"), [])

    def test_the_same_pattern_does_fire_on_a_genuine_word(self):
        config_no_boundary = cfg(situations=[
            {"when": ["class"], "say": "SITUATION"}])
        self.assertEqual(
            context.situation_blocks(config_no_boundary, "the class is broken"),
            ["SITUATION"])

    def test_a_pattern_that_already_has_a_boundary_is_not_double_wrapped(self):
        config_explicit = cfg(situations=[
            {"when": [r"\breact\b"], "say": "React behaviour is researched, not recalled."}])
        blocks = context.situation_blocks(config_explicit, "why does react rerender here")
        self.assertEqual(blocks, ["React behaviour is researched, not recalled."])


class BuildTests(unittest.TestCase):
    def test_core_comes_first_and_situations_follow(self):
        built = context.build(cfg(situations=[
            {"when": [r"\bx\b"], "say": "SITUATION"}]), "x")
        self.assertTrue(built.startswith("Before any factual claim"))
        self.assertTrue(built.rstrip().endswith("SITUATION"))

    def test_a_non_string_prompt_does_not_raise(self):
        self.assertIn("Before any factual claim", context.build(cfg(), None))


if __name__ == "__main__":
    unittest.main()
