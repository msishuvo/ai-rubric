import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_rubric import auth, discover
from ai_rubric.auth import authentication_error, usage_limit_error
from ai_rubric.config import Config


class AuthenticationErrorTest(unittest.TestCase):
    def test_expired_login_is_recognized_in_either_stream(self):
        messages = [
            "Login expired · Please run /login",
            "Failed to authenticate: OAuth session expired and could not be refreshed",
            "API Error: 401 OAuth token has expired. Please run /login",
            "OAuth token revoked · Please run /login",
            "Not logged in · Please run /login",
        ]
        for message in messages:
            for stdout, stderr in ((message, "warning: update available"), ("", message)):
                with self.subTest(message=message, stdout=bool(stdout)):
                    self.assertTrue(authentication_error("claude", stdout, stderr))

    def test_unrelated_errors_and_other_judges_are_not_reclassified(self):
        for message in ("connection timed out", "401 Invalid authentication credentials",
                        "Could not refresh your login because another Claude Code process is refreshing it",
                        "Your account is on hold", "permission denied"):
            with self.subTest(message=message):
                self.assertFalse(authentication_error("claude", "", message))
        self.assertFalse(authentication_error("agy", "Login expired · Please run /login", ""))


class UsageLimitErrorTest(unittest.TestCase):
    def test_usage_limits_of_host_models_are_recognized(self):
        for judge, message in (("codex", "You've hit your usage limit. Try again at 3:05 PM."),
                               ("claude", "You've hit your limit · resets 3pm (Europe/Berlin)"),
                               ("claude", "Claude AI usage limit reached|1767225600"),
                               ("claude", "5-hour limit reached ∙ resets 3pm")):
            with self.subTest(judge=judge, message=message):
                self.assertTrue(usage_limit_error(judge, "", message))

    def test_other_failures_and_gemini_are_not_usage_limits(self):
        for message in ("connection timed out", "Login expired · Please run /login",
                        "429 rate limit, retrying", "context window limit exceeded"):
            with self.subTest(message=message):
                self.assertFalse(usage_limit_error("codex", "", message))
        self.assertFalse(usage_limit_error("agy", "You've hit your usage limit", ""))

    def test_limit_on_stdout_survives_stderr_warnings(self):
        warnings = "\n".join(f"Warning: line {i}" for i in range(5))
        self.assertTrue(usage_limit_error("claude", "You've hit your limit \u00b7 resets 3pm", warnings))
        self.assertTrue(usage_limit_error("codex", "", warnings + "\nERROR: usage limit reached"))

    def test_echoed_brief_mentioning_a_usage_limit_is_ignored(self):
        echoed = "# Brief\nHow should the app warn users near their usage limit?\n"
        crash = echoed + "hook: SessionStart\nhook: SessionStart\nhook: SessionStart\nERROR: stream disconnected"
        self.assertFalse(usage_limit_error("codex", "", crash))
        real = echoed + "hook: SessionStart\nERROR: You\u2019ve hit your usage limit. Try again later."
        self.assertTrue(usage_limit_error("codex", "", real))


class InteractiveLoginTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.calls = self.root / "calls.jsonl"
        self.mode = self.root / "mode.json"
        self.mode.write_text("{}")
        self.cli = self.root / "claude custom"
        self.cli.write_text(f'''#!{sys.executable}
import json, sys
from pathlib import Path
args = sys.argv[1:]
with open({str(self.calls)!r}, "a") as f:
    f.write(json.dumps(args) + "\\n")
mode = json.loads(Path({str(self.mode)!r}).read_text())
if args == ["auth", "login", "--claudeai"]:
    sys.exit(mode.get("login_exit", 0))
if args == ["auth", "status", "--json"]:
    print(mode.get("status_text", json.dumps({{"loggedIn": True, "authMethod": mode.get("method", "claude.ai")}})))
    sys.exit(mode.get("status_exit", 0))
sys.exit(9)
''')
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IXUSR)
        self.cfg = Config(cli_paths={"claude": str(self.cli)})

    def terminals(self, interactive=True):
        stack = __import__("contextlib").ExitStack()
        incoming = stack.enter_context(mock.patch.object(sys, "stdin"))
        outgoing = stack.enter_context(mock.patch.object(sys, "stdout"))
        incoming.isatty.return_value = outgoing.isatty.return_value = interactive
        return stack

    def test_explicit_login_uses_subscription_and_checks_auth_source(self):
        with self.terminals():
            auth.login_claude(self.cfg, str(self.root))
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(calls, [["auth", "login", "--claudeai"], ["auth", "status", "--json"]])

    def test_unattended_login_never_launches_the_cli(self):
        with self.terminals(False), self.assertRaisesRegex(RuntimeError, "interactive terminal"):
            auth.login_claude(self.cfg, str(self.root))
        self.assertFalse(self.calls.exists())

    def test_failed_login_does_not_launch_status_or_a_judge(self):
        self.mode.write_text('{"login_exit": 1}')
        with self.terminals(), self.assertRaisesRegex(RuntimeError, "sign-in did not finish"):
            auth.login_claude(self.cfg, str(self.root))
        self.assertEqual(len(self.calls.read_text().splitlines()), 1)

    def test_status_requires_subscription_instead_of_an_override(self):
        for mode in ({"method": "api_key"}, {"method": "oauth_token"},
                     {"status_text": "not JSON"}, {"status_exit": 1},
                     {"status_text": '{"loggedIn": false, "authMethod": "claude.ai"}'}):
            with self.subTest(mode=mode):
                self.mode.write_text(json.dumps(mode))
                with self.terminals(), self.assertRaisesRegex(RuntimeError, "subscription authentication"):
                    auth.login_claude(self.cfg, str(self.root))

    def test_missing_cli_reports_actionable_error(self):
        with self.terminals(), mock.patch.dict(os.environ, {"PATH": str(self.root / "none")}), \
                mock.patch.dict(discover.KNOWN_LOCATIONS, {"claude": []}), \
                self.assertRaisesRegex(RuntimeError, "Claude CLI not found"):
            auth.login_claude(Config(), str(self.root))


if __name__ == "__main__":
    unittest.main()
