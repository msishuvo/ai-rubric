import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "consult" / "SKILL.md"


class SkillFileTest(unittest.TestCase):
    def setUp(self):
        text = SKILL.read_text()
        m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
        self.assertIsNotNone(m, "missing frontmatter")
        self.front, self.body = m.group(1), m.group(2)
        self.fields = dict(line.split(": ", 1) for line in self.front.splitlines() if ": " in line)

    def test_skill_frontmatter(self):
        self.assertEqual(self.fields.get("name"), "consult")
        desc = self.fields.get("description", "")
        self.assertLess(len(desc), 1024)
        self.assertIn("consult", desc)
        self.assertIn("no council", desc)

    def test_body_names_both_hosts_and_override(self):
        for needle in ("--from claude", "--from codex", "--allow-flagged"):
            self.assertIn(needle, self.body)

    def test_body_keeps_brief_exclusions_and_no_substitute(self):
        for needle in ("who wrote", "lean", "Never run a substitute", "unresolved",
                       "blocked by an approval", "Do not retry inside the sandbox"):
            self.assertIn(needle, self.body)


if __name__ == "__main__":
    unittest.main()
