"""Tests for rubric.transcript."""

import unittest

from rubric import transcript
from tests import builders as b


class CurrentTurnTests(unittest.TestCase):
    def test_the_turn_starts_after_the_last_human_prompt(self):
        records = [
            b.user("first"), b.assistant(b.text("one")),
            b.user("second"), b.assistant(b.text("two")),
        ]
        turn = transcript.current_turn(records)
        self.assertEqual(transcript.assistant_text(turn), "two")

    def test_hook_injections_do_not_start_a_turn(self):
        records = [
            b.user("real prompt"),
            b.meta_user("<system-reminder>injected</system-reminder>"),
            b.assistant(b.text("answer")),
        ]
        turn = transcript.current_turn(records)
        self.assertEqual(transcript.assistant_text(turn), "answer")

    def test_a_bracketed_system_block_does_not_start_a_turn(self):
        records = [
            b.user("real prompt"),
            b.user("<system-reminder>not the human</system-reminder>"),
            b.assistant(b.text("answer")),
        ]
        self.assertEqual(
            transcript.assistant_text(transcript.current_turn(records)), "answer")

    def test_subagent_records_are_dropped(self):
        records = [
            b.user("prompt"),
            b.sidechain_assistant(b.text("a subagent said fixed")),
            b.assistant(b.text("I am still looking")),
        ]
        turn = transcript.current_turn(records)
        self.assertNotIn("fixed", transcript.assistant_text(turn))

    def test_no_human_prompt_at_all_yields_every_record(self):
        records = [b.assistant(b.text("orphan"))]
        self.assertEqual(len(transcript.current_turn(records)), 1)


class AssistantTextTests(unittest.TestCase):
    def test_thinking_blocks_are_excluded(self):
        turn = [b.assistant(b.thinking("I think it is fixed"), b.text("Let me check."))]
        said = transcript.assistant_text(turn)
        self.assertIn("Let me check.", said)
        self.assertNotIn("fixed", said)

    def test_several_text_blocks_are_joined(self):
        turn = [b.assistant(b.text("one")), b.assistant(b.text("two"))]
        self.assertEqual(transcript.assistant_text(turn), "one\ntwo")

    def test_a_plain_string_content_field_is_handled(self):
        turn = [{"type": "assistant", "message": {"content": "plain"}}]
        self.assertEqual(transcript.assistant_text(turn), "plain")


class ToolTests(unittest.TestCase):
    def test_tool_uses_yield_name_input_and_id(self):
        turn = [b.assistant(b.bash("npm test", "abc"))]
        found = list(transcript.tool_uses(turn))
        self.assertEqual(found[0][0], "Bash")
        self.assertEqual(found[0][1]["command"], "npm test")
        self.assertEqual(found[0][2], "abc")

    def test_results_are_keyed_by_the_call_they_name(self):
        turn = [b.assistant(b.bash("npm test", "abc")), b.tool_result("2 passing", "abc")]
        self.assertIn("2 passing", transcript.tool_results(turn)["abc"])

    def test_an_unattributed_result_is_skipped_rather_than_guessed_at(self):
        turn = [{"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "orphan"}]}}]
        self.assertEqual(transcript.tool_results(turn), {})

    def test_a_list_shaped_result_body_is_flattened_to_text(self):
        turn = [{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "abc",
             "content": [{"type": "text", "text": "2 passing"}]}]}}]
        self.assertIn("2 passing", transcript.tool_results(turn)["abc"])


class ReadTests(unittest.TestCase):
    def test_a_malformed_line_is_skipped_rather_than_raising(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            handle.write('{"type":"user"}\nnot json\n{"type":"assistant"}\n')
            path = handle.name
        self.addCleanup(os.unlink, path)
        self.assertEqual(len(transcript.read(path)), 2)

    def test_a_missing_file_returns_an_empty_list(self):
        self.assertEqual(transcript.read("/no/such/transcript.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
