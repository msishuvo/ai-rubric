import unittest

from ai_rubric.commands import build_command
from ai_rubric.judges import JUDGES

DIRS = ["/x y", "/z"]


class BuildCommandTest(unittest.TestCase):
    def test_claude_command(self):
        self.assertEqual(
            build_command(JUDGES["claude"], "/bin/claude", "P", "/w", DIRS, "/o.md"),
            ["/bin/claude", "-p", "P", "--model", "claude-opus-5-5", "--effort", "medium",
             "--permission-mode", "plan", "--output-format", "text",
             "--add-dir", "/x y", "--add-dir", "/z"])

    def test_codex_command(self):
        self.assertEqual(
            build_command(JUDGES["codex"], "/bin/codex", "P", "/w", DIRS, "/o.md"),
            ["/bin/codex", "exec", "-m", "gpt-6-astra", "-c", 'model_reasoning_effort="medium"',
             "-s", "read-only", "-C", "/w", "--skip-git-repo-check", "--ephemeral",
             "-o", "/o.md", "P"])

    def test_agy_command(self):
        self.assertEqual(
            build_command(JUDGES["agy"], "/bin/agy", "P", "/w", DIRS, "/o.md"),
            ["/bin/agy", "-p", "P", "--model", "gemini-4-argon-high", "--mode", "plan",
             "--output-format", "text", "--add-dir", "/x y", "--add-dir", "/z"])

    def test_prompt_is_single_argv_element(self):
        prompt = 'a "b" $c `d`\nüñ ' + "x" * 50000
        for judge in JUDGES.values():
            argv = build_command(judge, "/bin/t", prompt, "/w", DIRS, "/o.md")
            self.assertEqual(argv.count(prompt), 1, judge.name)

    def test_no_write_flags(self):
        bad = {"workspace-write", "danger-full-access", "acceptEdits", "bypassPermissions",
               "accept-edits", "--dangerously-skip-permissions", "auto"}
        for judge in JUDGES.values():
            argv = build_command(judge, "/bin/t", "P", "/w", DIRS, "/o.md")
            self.assertFalse(bad & set(argv), judge.name)


if __name__ == "__main__":
    unittest.main()
