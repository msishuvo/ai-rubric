import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ai_rubric import cli
from ai_rubric.run import Verdict

REPO = Path(__file__).resolve().parents[1]


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.brief = Path(self.tmp.name, "brief.md")
        self.brief.write_text("Is this pricing plan worth shipping? Argue both ways.")
        self.cfg = Path(self.tmp.name, "none.toml")

    def call(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([*args, "--config", str(self.cfg)])
        return code, out.getvalue(), err.getvalue()

    def verdicts(self, *oks):
        names = ["codex", "agy"]
        return (Path("/saved/run"), [
            Verdict(n, f"model-{n}", ok, "## Verdict\nkeep" if ok else "", None if ok else "boom", 1.0)
            for n, ok in zip(names, oks)])

    def test_lint_refusal_exit_3_no_run(self):
        self.brief.write_text("I feel my plan is weak")
        with mock.patch.object(cli, "run_consult") as run:
            code, _, err = self.call("--from", "claude", "--brief", str(self.brief))
        self.assertEqual(code, 3)
        self.assertIn("may reveal authorship or leaning", err)
        run.assert_not_called()

    def test_allow_flagged_runs(self):
        self.brief.write_text("Should the Codex adapter be split?")
        with mock.patch.object(cli, "run_consult", return_value=self.verdicts(True, True)) as run:
            code, _, _ = self.call("--from", "claude", "--brief", str(self.brief), "--allow-flagged")
        self.assertEqual(code, 0)
        run.assert_called_once()

    def test_output_format_and_exit_0(self):
        with mock.patch.object(cli, "run_consult", return_value=self.verdicts(True, False)):
            code, out, _ = self.call("--from", "claude", "--brief", str(self.brief),
                                     "--add-dir", self.tmp.name)
        self.assertEqual(code, 0)
        self.assertIn("=== codex (model-codex) — ok ===\n## Verdict\nkeep", out)
        self.assertIn("=== agy (model-agy) — FAILED ===\nboom", out)
        self.assertTrue(out.rstrip().endswith("Saved: /saved/run"))

    def test_both_failed_exit_1(self):
        with mock.patch.object(cli, "run_consult", return_value=self.verdicts(False, False)):
            code, _, _ = self.call("--from", "codex", "--brief", str(self.brief))
        self.assertEqual(code, 1)

    def test_bad_host_exit_2(self):
        with self.assertRaises(SystemExit) as cm, redirect_stderr(io.StringIO()):
            cli.main(["--from", "gemini", "--brief", str(self.brief)])
        self.assertEqual(cm.exception.code, 2)

    def test_run_oserror_exit_2(self):
        with mock.patch.object(cli, "run_consult", side_effect=PermissionError("read-only fs")):
            code, _, err = self.call("--from", "claude", "--brief", str(self.brief))
        self.assertEqual(code, 2)
        self.assertIn("read-only fs", err)

    def test_missing_add_dir_exit_2_no_run(self):
        with mock.patch.object(cli, "run_consult") as run:
            code, _, err = self.call("--from", "claude", "--brief", str(self.brief),
                                     "--add-dir", "/no/such/folder")
        self.assertEqual(code, 2)
        self.assertIn("/no/such/folder", err)
        run.assert_not_called()

    def test_missing_config_extra_dir_exit_2_no_run(self):
        self.cfg.write_text('extra_dirs = ["/no/such/shared"]\n')
        with mock.patch.object(cli, "run_consult") as run:
            code, _, err = self.call("--from", "claude", "--brief", str(self.brief))
        self.assertEqual(code, 2)
        self.assertIn("/no/such/shared", err)
        run.assert_not_called()

    def test_missing_brief_exit_2(self):
        code, _, err = self.call("--from", "claude", "--brief", "/no/such/brief.md")
        self.assertEqual(code, 2)
        self.assertIn("brief", err)

    def test_resume_accepts_saved_run_without_a_new_brief_or_host(self):
        with mock.patch.object(cli, "resume_consult", create=True, return_value=self.verdicts(True, True)):
            code, out, _ = self.call("--resume", "/saved/run")
        self.assertEqual(code, 0)
        self.assertIn("Saved: /saved/run", out)

    def test_resume_rejects_new_context_flags(self):
        for flags in (("--from", "codex"), ("--add-dir", self.tmp.name), ("--allow-flagged",)):
            with self.subTest(flags=flags):
                code, _, err = self.call("--resume", "/saved/run", *flags)
                self.assertEqual(code, 2)
                self.assertIn("saved context", err)

    def test_login_requires_resume(self):
        code, _, err = self.call("--from", "codex", "--brief", str(self.brief), "--login")
        self.assertEqual(code, 2)
        self.assertIn("--resume", err)

    def test_fresh_run_still_requires_host(self):
        code, _, err = self.call("--brief", str(self.brief))
        self.assertEqual(code, 2)
        self.assertIn("--from", err)

    def test_partial_auth_failure_prints_quoted_recovery_commands(self):
        verdicts = [Verdict("claude", "claude-opus-5-5", False, "", "Login expired", 1.0,
                            "authentication_required"),
                    Verdict("agy", "gemini-4-neon-high", True, "keep", None, 1.0)]
        with mock.patch.object(cli, "run_consult", return_value=(Path("/saved/run with spaces"), verdicts)):
            code, out, _ = self.call("--from", "codex", "--brief", str(self.brief))
        self.assertEqual(code, 0)
        self.assertIn("PARTIAL: 1 of 2 judges", out)
        self.assertIn("auth login --claudeai", out)
        self.assertIn("consult --resume '/saved/run with spaces'", out)
        self.assertIn("--login", out)

    def test_agy_host_runs_and_names_carbon_stand_in(self):
        verdicts = [Verdict("claude", "claude-opus-5-5", True, "keep", None, 1.0),
                    Verdict("agy", "gemini-4-carbon-high", True, "keep", None, 1.0)]
        with mock.patch.object(cli, "run_consult", return_value=(Path("/saved/run"), verdicts)) as run:
            code, out, _ = self.call("--from", "agy", "--brief", str(self.brief))
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.args[0], "agy")
        self.assertIn("gemini-4-carbon-high was called in its place", out)

    def test_carbon_judge_from_claude_host_is_not_called_a_stand_in(self):
        with mock.patch.object(cli, "run_consult", return_value=self.verdicts(True, True)):
            _, out, _ = self.call("--from", "claude", "--brief", str(self.brief))
        self.assertNotIn("in its place", out)

    def test_resumed_agy_run_reads_host_from_manifest(self):
        run_dir = Path(self.tmp.name, "run")
        run_dir.mkdir()
        (run_dir / "run.json").write_text('{"host": "agy"}')
        verdicts = [Verdict("neon", "gemini-4-neon-high", True, "keep", None, 1.0),
                    Verdict("codex", "gpt-6.2-astra", True, "keep", None, 1.0)]
        with mock.patch.object(cli, "resume_consult", return_value=(run_dir, verdicts)):
            _, out, _ = self.call("--resume", str(run_dir))
        self.assertIn("gemini-4-neon-high was called in its place", out)

    def test_version_flag_prints_the_version(self):
        from ai_rubric import __version__
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"consult {__version__}")
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_cancel_names_the_folder_to_resume(self):
        def interrupted(*a, **k):
            exc = KeyboardInterrupt()
            exc.run_dir = Path("/saved/run with spaces")
            raise exc
        with mock.patch.object(cli, "run_consult", side_effect=interrupted):
            code, _, err = self.call("--from", "codex", "--brief", str(self.brief))
        self.assertEqual(code, 130)
        self.assertIn("consult --resume '/saved/run with spaces'", err)
        with mock.patch.object(cli, "resume_consult", side_effect=KeyboardInterrupt):
            code, _, err = self.call("--resume", "/saved/run")
        self.assertEqual(code, 130)
        self.assertIn("consult --resume /saved/run", err)

    def test_resume_failure_is_actionable_exit_2(self):
        with mock.patch.object(cli, "resume_consult", create=True, side_effect=RuntimeError("bad manifest")):
            code, _, err = self.call("--resume", "/saved/run")
        self.assertEqual(code, 2)
        self.assertIn("bad manifest", err)

    def test_old_python_restarts_with_the_installed_python(self):
        old = "/usr/bin/python3"
        probe = subprocess.run([old, "-c", "import sys; print(sys.version_info < (3, 11))"],
                               capture_output=True, text=True) if os.path.exists(old) else None
        if not probe or probe.stdout.strip() != "True":
            self.skipTest("needs an older /usr/bin/python3")
        home = Path(self.tmp.name, "home")
        saved = home / ".local/state/ai-rubric/python"
        saved.parent.mkdir(parents=True)
        env = {**os.environ, "HOME": str(home)}
        proc = subprocess.run([old, str(REPO / "bin/consult"), "--version"], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("./install.sh", proc.stderr)
        saved.write_text(sys.executable + "\n")
        proc = subprocess.run([old, str(REPO / "bin/consult"), "--version"], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("consult ", proc.stdout)

    def test_bin_works_through_symlink(self):
        link = Path(self.tmp.name, "consult")
        link.symlink_to(REPO / "bin" / "consult")
        proc = subprocess.run([sys.executable, str(link), "--help"], capture_output=True,
                              text=True, cwd=self.tmp.name)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--from", proc.stdout)
        self.assertTrue(os.access(REPO / "bin" / "consult", os.X_OK))


if __name__ == "__main__":
    unittest.main()
