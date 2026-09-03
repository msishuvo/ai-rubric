"""Tests for rubric.config."""

import json
import os
import tempfile
import unittest

from rubric import config


class DeepMergeTests(unittest.TestCase):
    def test_overlay_replaces_scalar(self):
        merged = config.deep_merge({"who": "a"}, {"who": "b"})
        self.assertEqual(merged["who"], "b")

    def test_nested_objects_merge_rather_than_replace(self):
        base = {"gate": {"enabled": True, "requires_work_change": True}}
        merged = config.deep_merge(base, {"gate": {"enabled": False}})
        self.assertEqual(merged["gate"]["enabled"], False)
        self.assertEqual(merged["gate"]["requires_work_change"], True)

    def test_arrays_replace_by_default(self):
        merged = config.deep_merge({"claims": ["a", "b"]}, {"claims": ["c"]})
        self.assertEqual(merged["claims"], ["c"])

    def test_trailing_plus_appends_instead(self):
        merged = config.deep_merge({"claims": ["a", "b"]}, {"claims+": ["c"]})
        self.assertEqual(merged["claims"], ["a", "b", "c"])

    def test_trailing_plus_on_absent_key_creates_it(self):
        merged = config.deep_merge({}, {"claims+": ["c"]})
        self.assertEqual(merged["claims"], ["c"])

    def test_trailing_plus_works_inside_nested_object(self):
        base = {"evidence": {"commands": ["make"]}}
        merged = config.deep_merge(base, {"evidence": {"commands+": ["npm test"]}})
        self.assertEqual(merged["evidence"]["commands"], ["make", "npm test"])

    def test_a_bare_string_overlay_is_wrapped_not_shredded(self):
        merged = config.deep_merge({"claims": ["a"]}, {"claims+": "b"})
        self.assertEqual(merged["claims"], ["a", "b"])

    def test_a_list_overlay_still_appends_each_element(self):
        merged = config.deep_merge({"claims": ["a"]}, {"claims+": ["c"]})
        self.assertEqual(merged["claims"], ["a", "c"])

    def test_a_none_overlay_value_behaves_as_before(self):
        merged = config.deep_merge({"claims": ["a"]}, {"claims+": None})
        self.assertEqual(merged["claims"], ["a"])


class ReadJsonTests(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(config.read_json("/no/such/path/rubric.json"))

    def test_malformed_json_returns_none_rather_than_raising(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{ not json")
            path = handle.name
        self.addCleanup(os.unlink, path)
        self.assertIsNone(config.read_json(path))


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.home = tempfile.mkdtemp()

    def write(self, root, payload):
        os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
        with open(os.path.join(root, ".claude", "rubric.json"), "w") as handle:
            json.dump(payload, handle)

    def test_no_config_anywhere_reports_unconfigured_and_gate_off(self):
        loaded, configured = config.load(self.project, self.home)
        self.assertFalse(configured)
        self.assertFalse(loaded["gate"]["enabled"])

    def test_project_config_turns_the_gate_on_by_default(self):
        self.write(self.project, {"who": "msishuvo"})
        loaded, configured = config.load(self.project, self.home)
        self.assertTrue(configured)
        self.assertTrue(loaded["gate"]["enabled"])
        self.assertEqual(loaded["who"], "msishuvo")

    def test_project_config_can_turn_the_gate_off_explicitly(self):
        self.write(self.project, {"gate": {"enabled": False}})
        loaded, _ = config.load(self.project, self.home)
        self.assertFalse(loaded["gate"]["enabled"])

    def test_user_config_alone_does_not_enable_the_gate(self):
        self.write(self.home, {"who": "msishuvo"})
        loaded, configured = config.load(self.project, self.home)
        self.assertFalse(configured)
        self.assertFalse(loaded["gate"]["enabled"])
        self.assertEqual(loaded["who"], "msishuvo")

    def test_project_config_wins_over_user_config(self):
        self.write(self.home, {"who": "device-level"})
        self.write(self.project, {"who": "project-level"})
        loaded, _ = config.load(self.project, self.home)
        self.assertEqual(loaded["who"], "project-level")

    def test_every_default_key_is_present_even_with_no_config(self):
        loaded, _ = config.load(self.project, self.home)
        for key in ("dialect", "who", "cannot_check", "work_files", "evidence",
                    "claims", "disclaimers", "gate", "cost_table",
                    "situations", "invariants"):
            self.assertIn(key, loaded)

    def test_project_config_with_malformed_gate_does_not_raise(self):
        self.write(self.project, {"gate": "off"})
        loaded, configured = config.load(self.project, self.home)
        self.assertTrue(configured)
        self.assertIsInstance(loaded["gate"], dict)
        self.assertIn("enabled", loaded["gate"])

    def test_user_config_with_malformed_gate_does_not_raise(self):
        self.write(self.home, {"gate": "off"})
        loaded, configured = config.load(self.project, self.home)
        self.assertFalse(configured)
        self.assertIsInstance(loaded["gate"], dict)
        self.assertIn("enabled", loaded["gate"])


if __name__ == "__main__":
    unittest.main()
