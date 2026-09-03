"""Tests for the shipped dialect presets.

These assert shape and a few load-bearing behaviours, not every regex. The
point is that a preset cannot introduce a key the config does not know
about, and that the claim patterns catch what they are meant to catch
while leaving ordinary prose alone.
"""

import json
import os
import re
import tempfile
import unittest

from rubric import config

PRESETS = os.path.join(config.PLUGIN_ROOT, "presets")


def load_preset(name):
    with open(os.path.join(PRESETS, name + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


def matches(patterns, text):
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


class PresetShapeTests(unittest.TestCase):
    def test_both_presets_exist_and_parse(self):
        for name in ("code", "research"):
            self.assertIsInstance(load_preset(name), dict)

    def test_presets_introduce_no_unknown_top_level_keys(self):
        known = set(config.DEFAULTS)
        for name in ("code", "research"):
            for key in load_preset(name):
                self.assertIn(key.rstrip("+"), known, "%s in %s" % (key, name))


class CodePresetTests(unittest.TestCase):
    def setUp(self):
        self.preset = load_preset("code")

    def test_claims_catch_a_completion_statement(self):
        for said in ("Fixed the parser.", "That now works.", "Tests are passing.",
                     "Verified against the store."):
            self.assertTrue(matches(self.preset["claims"], said), said)

    def test_bare_working_is_not_a_claim(self):
        for innocent in ("the working directory", "our working agreement",
                         "I am working on it"):
            self.assertFalse(matches(self.preset["claims"], innocent), innocent)

    def test_the_sanctioned_disclaimer_is_recognised(self):
        self.assertTrue(matches(self.preset["disclaimers"], "I have not checked this."))

    def test_gate_keys_on_work_changing(self):
        self.assertTrue(self.preset["gate"]["requires_work_change"])


class ResearchPresetTests(unittest.TestCase):
    def setUp(self):
        self.preset = load_preset("research")

    def test_claims_catch_an_assertion_about_a_source(self):
        for said in ("The paper says the effect vanishes.",
                     "According to the 2024 report, adoption doubled.",
                     "62% of respondents disagreed."):
            self.assertTrue(matches(self.preset["claims"], said), said)

    def test_ordinary_prose_is_not_a_claim(self):
        for innocent in ("Let me read the paper.", "I will check the data.",
                         "What does the report cover?"):
            self.assertFalse(matches(self.preset["claims"], innocent), innocent)

    def test_gate_does_not_require_an_edit(self):
        self.assertFalse(self.preset["gate"]["requires_work_change"])

    def test_reading_tools_count_as_evidence(self):
        self.assertIn("Read", self.preset["evidence"]["tools"])
        self.assertIn("WebFetch", self.preset["evidence"]["tools"])


class DialectResolutionTests(unittest.TestCase):
    def test_naming_a_dialect_inherits_its_claims(self):
        project = tempfile.mkdtemp()
        home = tempfile.mkdtemp()
        os.makedirs(os.path.join(project, ".claude"))
        with open(os.path.join(project, ".claude", "rubric.json"), "w") as handle:
            json.dump({"dialect": "code"}, handle)
        loaded, configured = config.load(project, home)
        self.assertTrue(configured)
        self.assertTrue(matches(loaded["claims"], "Fixed it."))

    def test_a_bogus_dialect_name_cannot_traverse_the_filesystem(self):
        self.assertEqual(config.read_preset("../../etc/passwd"), {})


if __name__ == "__main__":
    unittest.main()
