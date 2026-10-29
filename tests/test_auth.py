import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_rubric import auth, discover
from ai_rubric.auth import authentication_error
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
