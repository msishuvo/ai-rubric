import unittest

from ai_rubric.judges import FALLBACK, JUDGES, Judge, judges_for, stand_ins_for


class JudgesForTest(unittest.TestCase):
    def test_claude_host_gets_codex_and_agy(self):
        self.assertEqual([j.name for j in judges_for("claude")], ["codex", "agy"])

    def test_codex_host_gets_claude_and_agy(self):
        self.assertEqual([j.name for j in judges_for("codex")], ["claude", "agy"])

    def test_agy_host_gets_claude_and_codex(self):
        self.assertEqual([j.name for j in judges_for("agy")], ["claude", "codex"])

    def test_stand_ins_per_host(self):
        self.assertEqual(stand_ins_for("claude"), [FALLBACK])
        self.assertEqual(stand_ins_for("codex"), [FALLBACK])
        self.assertEqual(stand_ins_for("agy"), [JUDGES["agy"], FALLBACK])
        with self.assertRaises(ValueError):
            stand_ins_for("gemini")

    def test_models_are_pinned(self):
        self.assertEqual(JUDGES["claude"], Judge("claude", "claude-opus-5-5", "high"))
        self.assertEqual(JUDGES["codex"], Judge("codex", "gpt-6.2-astra", "high"))
        self.assertEqual(JUDGES["agy"], Judge("agy", "gemini-4-carbon-high", None))
        self.assertEqual(FALLBACK, Judge("neon", "gemini-4-neon-high", None, cli="agy"))

    def test_unknown_host_rejected(self):
        for host in ("gemini", "antigravity", ""):
            with self.assertRaises(ValueError):
                judges_for(host)


if __name__ == "__main__":
    unittest.main()
