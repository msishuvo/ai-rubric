import unittest

from ai_rubric.prompt import build_prompt, lint_brief

HEADINGS = ["## Case for", "## Case against", "## Verdict", "## Missing",
            "## Evidence", "## Not checked"]


class BuildPromptTest(unittest.TestCase):
    def test_prompt_has_all_headings(self):
        prompt = build_prompt("b", ["/w"])
        for heading in HEADINGS:
            self.assertIn(heading, prompt)

    def test_prompt_lists_roots_and_keeps_brief(self):
        brief = "Question: is it sound?\n\nDetails `x` $y"
        prompt = build_prompt(brief, ["/a b", "/c"])
        lines = prompt.splitlines()
        self.assertIn("- /a b", lines)
        self.assertIn("- /c", lines)
        self.assertTrue(prompt.endswith(brief))

    def test_prompt_forbids_edits(self):
        self.assertIn("Do not edit", build_prompt("b", ["/w"]))


class LintBriefTest(unittest.TestCase):
    def test_lint_flags_tool_names(self):
        self.assertIn("Codex", lint_brief("Codex agreed with this"))

    def test_lint_flags_leaning(self):
        self.assertTrue(lint_brief("I feel this plan is weak"))

    def test_lint_flags_authorship(self):
        self.assertTrue(lint_brief("Review my proposal"))

    def test_lint_clean_brief(self):
        self.assertEqual(lint_brief("Is this pricing plan worth shipping? Argue both ways."), [])

    def test_lint_ignores_substrings(self):
        self.assertEqual(lint_brief("the gptools directory and claudette module"), [])


if __name__ == "__main__":
    unittest.main()
