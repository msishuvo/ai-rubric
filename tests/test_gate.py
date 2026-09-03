"""Tests for rubric.gate.

Every one of the gate's conditions gets a test that turns it off on its
own, because the whole design rests on the conjunction being tight. A gate
that cries wolf gets switched off, and then it protects nothing.
"""

import unittest

from rubric import config, gate
from tests import builders as b


def code_config(**overrides):
    loaded = dict(config.DEFAULTS)
    loaded["evidence"] = dict(config.DEFAULTS["evidence"])
    loaded["gate"] = dict(config.DEFAULTS["gate"])
    loaded.update({
        "claims": [r"\bfixed\b", r"\bpassing\b"],
        "disclaimers": [r"i have not checked this"],
        "work_files": ["src/**/*.py"],
        "evidence": {"commands": [r"\bpytest\b"], "tools": [],
                     "never_started": ["no tests ran"]},
        "gate": {"enabled": True, "requires_work_change": True},
        "cost_table": [{"claim": "the tests pass", "check": "pytest -q",
                        "cost": "~20s"}],
    })
    loaded.update(overrides)
    return loaded


def turn_of(*records):
    return list(records)


class BlockingTests(unittest.TestCase):
    def test_it_blocks_a_claim_with_an_edit_and_no_command(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed.")))
        self.assertIsNotNone(gate.decide(code_config(), gate.signals(code_config(), turn)))

    def test_the_reason_names_a_check_from_the_cost_table(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed.")))
        verdict = gate.decide(code_config(), gate.signals(code_config(), turn))
        self.assertIn("pytest -q", verdict.reason)

    def test_the_reason_quotes_the_claim_it_objected_to(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed.")))
        verdict = gate.decide(code_config(), gate.signals(code_config(), turn))
        self.assertIn("Fixed", verdict.reason)

    def test_the_reason_contains_no_em_dash(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed.")))
        verdict = gate.decide(code_config(), gate.signals(code_config(), turn))
        self.assertNotIn("—", verdict.reason)


class EachConditionAloneAllowsTests(unittest.TestCase):
    def allowed(self, turn, cfg=None):
        cfg = cfg or code_config()
        return gate.decide(cfg, gate.signals(cfg, turn))

    def test_no_claim_allows(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"), b.text("Renamed a variable.")))
        self.assertIsNone(self.allowed(turn))

    def test_a_disclaimer_allows(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"),
                                   b.text("Fixed. I have not checked this.")))
        self.assertIsNone(self.allowed(turn))

    def test_no_work_change_allows(self):
        turn = turn_of(b.assistant(b.text("Fixed.")))
        self.assertIsNone(self.allowed(turn))

    def test_an_edit_outside_work_files_allows(self):
        turn = turn_of(b.assistant(b.edit("/proj/README.md"), b.text("Fixed.")))
        self.assertIsNone(self.allowed(turn))

    def test_evidence_allows(self):
        turn = turn_of(
            b.assistant(b.edit("/proj/src/a.py", "e1"), b.bash("pytest -q", "t1"),
                        b.text("Fixed.")),
            b.tool_result("3 passed", "t1"))
        self.assertIsNone(self.allowed(turn))

    def test_the_gate_being_disabled_allows(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed.")))
        cfg = code_config(gate={"enabled": False, "requires_work_change": True})
        self.assertIsNone(self.allowed(turn, cfg))

    def test_a_claim_only_in_thinking_allows(self):
        turn = turn_of(b.assistant(b.edit("/proj/src/a.py"),
                                   b.thinking("it is fixed"), b.text("Let me look.")))
        self.assertIsNone(self.allowed(turn))


class NeverStartedTests(unittest.TestCase):
    def test_a_command_whose_output_says_it_never_started_is_not_evidence(self):
        cfg = code_config()
        turn = turn_of(
            b.assistant(b.edit("/proj/src/a.py", "e1"), b.bash("pytest -q", "t1"),
                        b.text("Fixed, tests passing.")),
            b.tool_result("no tests ran", "t1"))
        self.assertIsNotNone(gate.decide(cfg, gate.signals(cfg, turn)))

    def test_a_second_genuine_run_still_counts_as_evidence(self):
        cfg = code_config()
        turn = turn_of(
            b.assistant(b.edit("/proj/src/a.py", "e1"),
                        b.bash("pytest -q", "t1"), b.bash("pytest -q src", "t2"),
                        b.text("Fixed.")),
            b.tool_result("no tests ran", "t1"),
            b.tool_result("3 passed", "t2"))
        self.assertIsNone(gate.decide(cfg, gate.signals(cfg, turn)))


class BashWriteTests(unittest.TestCase):
    def test_a_shell_redirect_into_a_work_file_counts_as_a_change(self):
        cfg = code_config()
        turn = turn_of(b.assistant(b.bash("cat > src/a.py <<EOF", "t1"), b.text("Fixed.")))
        self.assertTrue(gate.signals(cfg, turn).work_changed)

    def test_sed_in_place_on_a_work_file_counts(self):
        cfg = code_config()
        turn = turn_of(b.assistant(b.bash("sed -i '' s/a/b/ src/a.py", "t1"),
                                   b.text("Fixed.")))
        self.assertTrue(gate.signals(cfg, turn).work_changed)

    def test_merely_mentioning_a_work_file_does_not_count(self):
        cfg = code_config()
        turn = turn_of(b.assistant(b.bash("grep -n foo src/a.py", "t1"), b.text("Fixed.")))
        self.assertFalse(gate.signals(cfg, turn).work_changed)


class ResearchDialectTests(unittest.TestCase):
    def research_config(self):
        loaded = code_config()
        loaded.update({
            "claims": [r"\bthe paper says\b", r"\b\d+% of\b"],
            "disclaimers": [r"i have not checked this"],
            "evidence": {"commands": [], "tools": ["Read", "WebFetch"],
                         "never_started": ["404"]},
            "gate": {"enabled": True, "requires_work_change": False},
            "cost_table": [{"claim": "the paper says X", "check": "open the paper",
                            "cost": "~60s"}],
        })
        return loaded

    def test_a_claim_about_a_source_with_nothing_opened_blocks(self):
        cfg = self.research_config()
        turn = turn_of(b.assistant(b.text("The paper says the effect vanishes.")))
        self.assertIsNotNone(gate.decide(cfg, gate.signals(cfg, turn)))

    def test_having_read_something_allows(self):
        cfg = self.research_config()
        turn = turn_of(
            b.assistant(b.tool_use("Read", {"file_path": "/p/paper.md"}, "t1"),
                        b.text("The paper says the effect vanishes.")),
            b.tool_result("...text...", "t1"))
        self.assertIsNone(gate.decide(cfg, gate.signals(cfg, turn)))

    def test_a_fetch_that_404ed_is_not_evidence(self):
        cfg = self.research_config()
        turn = turn_of(
            b.assistant(b.tool_use("WebFetch", {"url": "http://x"}, "t1"),
                        b.text("The paper says the effect vanishes.")),
            b.tool_result("404 Not Found", "t1"))
        self.assertIsNotNone(gate.decide(cfg, gate.signals(cfg, turn)))


class MisconfigurationTests(unittest.TestCase):
    def test_it_fires_when_work_files_is_empty_and_requires_work_change_is_true(self):
        cfg = code_config(work_files=[])
        verdict = gate.misconfiguration_verdict(cfg)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, "misconfigured")
        self.assertIn("work_files", verdict.reason)

    def test_it_does_not_fire_when_work_files_is_genuinely_configured(self):
        cfg = code_config(work_files=["src/**/*.py"])
        self.assertIsNone(gate.misconfiguration_verdict(cfg))

    def test_it_does_not_fire_when_requires_work_change_is_false(self):
        cfg = code_config(work_files=[],
                           gate={"enabled": True, "requires_work_change": False})
        self.assertIsNone(gate.misconfiguration_verdict(cfg))

    def test_it_does_not_fire_when_the_gate_is_disabled(self):
        cfg = code_config(work_files=[],
                           gate={"enabled": False, "requires_work_change": True})
        self.assertIsNone(gate.misconfiguration_verdict(cfg))

    def test_a_non_list_work_files_value_also_counts_as_unset(self):
        cfg = code_config(work_files=None)
        self.assertIsNotNone(gate.misconfiguration_verdict(cfg))

    def test_decide_surfaces_the_misconfiguration_verdict_even_with_no_claim(self):
        cfg = code_config(work_files=[])
        turn = turn_of(b.assistant(b.text("Just discussing, no claim here.")))
        verdict = gate.decide(cfg, gate.signals(cfg, turn))
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, "misconfigured")

    def test_decide_does_not_misconfigure_when_work_files_present_and_no_claim(self):
        cfg = code_config()
        turn = turn_of(b.assistant(b.text("Just discussing, no claim here.")))
        self.assertIsNone(gate.decide(cfg, gate.signals(cfg, turn)))


class EvaluateTests(unittest.TestCase):
    def test_stop_hook_active_allows_without_looking(self):
        records = [b.user("go"), b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed."))]
        self.assertIsNone(gate.evaluate(code_config(), records, stop_hook_active=True))

    def test_evaluate_finds_the_same_verdict_as_decide(self):
        records = [b.user("go"), b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed."))]
        self.assertIsNotNone(gate.evaluate(code_config(), records))

    def test_a_previous_turn_is_not_this_turn(self):
        records = [
            b.user("one"), b.assistant(b.edit("/proj/src/a.py"), b.text("Fixed.")),
            b.user("two"), b.assistant(b.text("Here is an explanation.")),
        ]
        self.assertIsNone(gate.evaluate(code_config(), records))


if __name__ == "__main__":
    unittest.main()
