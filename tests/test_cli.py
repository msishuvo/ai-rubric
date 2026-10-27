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
                                     "--add-dir", "/a")
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

    def test_missing_brief_exit_2(self):
        code, _, err = self.call("--from", "claude", "--brief", "/no/such/brief.md")
        self.assertEqual(code, 2)
        self.assertIn("brief", err)

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
