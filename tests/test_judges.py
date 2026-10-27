import unittest

from ai_rubric.judges import JUDGES, Judge, judges_for


class JudgesForTest(unittest.TestCase):
    def test_claude_host_gets_codex_and_agy(self):
        self.assertEqual([j.name for j in judges_for("claude")], ["codex", "agy"])

    def test_codex_host_gets_claude_and_agy(self):
        self.assertEqual([j.name for j in judges_for("codex")], ["claude", "agy"])

    def test_models_are_pinned(self):
        self.assertEqual(JUDGES["claude"], Judge("claude", "claude-opus-5-5", "medium"))
        self.assertEqual(JUDGES["codex"], Judge("codex", "gpt-6-astra", "medium"))
        self.assertEqual(JUDGES["agy"], Judge("agy", "gemini-4-argon-high", None))

    def test_unknown_host_rejected(self):
        for host in ("agy", "gemini", ""):
            with self.assertRaises(ValueError):
                judges_for(host)


if __name__ == "__main__":
    unittest.main()
