import json
import tempfile
import unittest
from pathlib import Path

from ai_rubric.agy_settings import READ_ONLY_RULES, add_rules, remove_rules


class AgySettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Path(self.tmp.name, "settings.json")
        self.state = Path(self.tmp.name, "state", "agy-added.json")

    def read(self):
        return json.loads(self.settings.read_text())

    def test_rules_are_read_only_commands(self):
        for risky in ("find", "rg", "tree", "file", "sed", "awk", "git diff", "git log", "git show"):
            self.assertNotIn(f"command({risky})", READ_ONLY_RULES)
        self.assertFalse([r for r in READ_ONLY_RULES if r.startswith("command(git")])
        self.assertIn("command(cat)", READ_ONLY_RULES)

    def test_add_keeps_other_keys(self):
        self.settings.write_text(json.dumps({"model": "M", "trustedWorkspaces": ["/a"]}))
        add_rules(self.settings, self.state)
        data = self.read()
        self.assertEqual(data["model"], "M")
        self.assertEqual(data["trustedWorkspaces"], ["/a"])
        self.assertEqual(data["permissions"]["allow"], READ_ONLY_RULES)

    def test_add_keeps_indent_and_non_ascii(self):
        self.settings.write_text('{\n    "name": "S\u00f8ren"\n}\n', encoding="utf-8")
        add_rules(self.settings, self.state)
        text = self.settings.read_text(encoding="utf-8")
        self.assertIn('"S\u00f8ren"', text)
        self.assertNotIn("\\u00f8", text)
        self.assertIn('\n    "name"', text)

    def test_add_is_idempotent(self):
        self.settings.write_text("{}")
        add_rules(self.settings, self.state)
        first = self.settings.read_text()
        add_rules(self.settings, self.state)
        self.assertEqual(self.settings.read_text(), first)

    def test_remove_keeps_users_own_rules(self):
        self.settings.write_text(json.dumps({"permissions": {"allow": ["command(ls)", "command(make)"]}}))
        add_rules(self.settings, self.state)
        remove_rules(self.settings, self.state)
        self.assertEqual(self.read(), {"permissions": {"allow": ["command(ls)", "command(make)"]}})
        self.assertFalse(self.state.exists())

    def test_remove_without_state_falls_back_to_known_rules(self):
        self.settings.write_text(json.dumps({"permissions": {"allow": ["command(make)"]}}))
        add_rules(self.settings, self.state)
        self.state.unlink()
        remove_rules(self.settings, self.state)
        self.assertEqual(self.read(), {"permissions": {"allow": ["command(make)"]}})

    def test_remove_drops_empty_permissions(self):
        self.settings.write_text(json.dumps({"model": "M"}))
        add_rules(self.settings, self.state)
        remove_rules(self.settings, self.state)
        self.assertEqual(self.read(), {"model": "M"})

    def test_missing_settings_file_created_and_removed_cleanly(self):
        add_rules(self.settings, self.state)
        self.assertEqual(self.read()["permissions"]["allow"], READ_ONLY_RULES)
        remove_rules(self.settings, self.state)
        self.assertEqual(self.read(), {})


if __name__ == "__main__":
    unittest.main()
