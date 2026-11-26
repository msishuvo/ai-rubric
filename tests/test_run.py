import os
import stat
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from ai_rubric import discover
from ai_rubric.config import Config
from ai_rubric.judges import FALLBACK, JUDGES
from ai_rubric import run as run_module
from ai_rubric.run import make_run_dir, run_consult

VERDICT = "## Verdict\\nkeep"

# A fake judge CLI. Writes its text to the file after -o if given (as codex does),
# otherwise prints it. BODY is substituted per test.
FAKE = """#!{py}
import sys, time
args = sys.argv[1:]
text = {text!r}
{body}
if "-o" in args:
    open(args[args.index("-o") + 1], "w").write(text)
else:
    sys.stdout.write(text)
"""


class RunConsultTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ws = self.dir / "work space"
        self.ws.mkdir()
        self.save = self.dir / "save"
        patches = [mock.patch.dict(os.environ, {"PATH": str(self.dir / "nothing")}),
                   mock.patch.dict(discover.KNOWN_LOCATIONS, {"agy": [], "codex": [], "claude": []})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def fake(self, name, text="## Verdict\nkeep", body=""):
        path = self.dir / f"fake-{name}"
        path.write_text(FAKE.format(py=sys.executable, text=text, body=body))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def config(self, **kw):
        return Config(save_root=str(self.save), **kw)

    def test_both_judges_succeed(self):
        cfg = self.config(cli_paths={"codex": self.fake("codex"), "agy": self.fake("agy")})
        run_dir, verdicts = run_consult("claude", "Is it sound?", str(self.ws), [], cfg)
        self.assertEqual([v.judge for v in verdicts], ["codex", "agy"])
        self.assertTrue(all(v.ok for v in verdicts))
        self.assertIn("keep", verdicts[0].text)
        for f in ("brief.md", "prompt.md", "codex.md", "agy.md", "run.log"):
            self.assertTrue((run_dir / f).is_file(), f)

    def test_missing_cli_reported_not_substituted(self):
        cfg = self.config(cli_paths={"agy": self.fake("agy"), "claude": self.fake("claude")})
        _, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        names = [v.judge for v in verdicts]
        self.assertEqual(names, ["codex", "agy"])
        codex = verdicts[0]
        self.assertFalse(codex.ok)
        self.assertIn("not found", codex.error)
        self.assertNotIn("claude", names)

    def test_hanging_judge_times_out_other_saved(self):
        cfg = self.config(timeout=2, cli_paths={"codex": self.fake("codex"),
                                                "agy": self.fake("agy", body="time.sleep(30)")})
        start = time.monotonic()
        run_dir, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertLess(time.monotonic() - start, 10)
        codex, agy = verdicts
        self.assertTrue(codex.ok)
        self.assertFalse(agy.ok)
        self.assertIn("timed out", agy.error)
        self.assertIn("keep", (run_dir / "codex.md").read_text())
        self.assertTrue((run_dir / "agy.md").read_text().startswith("FAILED:"))

    def test_empty_output_is_failure(self):
        cfg = self.config(cli_paths={"codex": self.fake("codex", text="  \n"),
                                     "agy": self.fake("agy")})
        _, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertFalse(verdicts[0].ok)
        self.assertEqual(verdicts[0].error, "empty verdict")

    def test_empty_output_includes_stderr_reason(self):
        body = "sys.stderr.write('a tool required the command permission\\n')"
        cfg = self.config(cli_paths={"codex": self.fake("codex"),
                                     "agy": self.fake("agy", text="", body=body)})
        _, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertFalse(verdicts[1].ok)
        self.assertTrue(verdicts[1].error.startswith("empty verdict"))
        self.assertIn("required the command permission", verdicts[1].error)

    def test_undecodable_output_does_not_lose_other_verdict(self):
        body = "sys.stdout.buffer.write(b'\\xff## Verdict'); sys.stdout.flush(); sys.exit(0)"
        cfg = self.config(cli_paths={"codex": self.fake("codex"),
                                     "agy": self.fake("agy", body=body)})
        run_dir, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertTrue(verdicts[0].ok)
        self.assertIn("keep", (run_dir / "codex.md").read_text())

    def test_unexpected_error_in_one_judge_is_contained(self):
        cfg = self.config(cli_paths={"codex": self.fake("codex"), "agy": self.fake("agy")})
        real = run_module.build_command

        def boom(judge, *a, **k):
            if judge.name == "agy":
                raise RuntimeError("kaboom")
            return real(judge, *a, **k)
        with mock.patch.object(run_module, "build_command", boom):
            _, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertTrue(verdicts[0].ok)
        self.assertFalse(verdicts[1].ok)
        self.assertIn("kaboom", verdicts[1].error)

    def test_timeout_kills_judge_children(self):
        pidfile = self.dir / "child.pid"
        wrapper = self.dir / "fake-agy-wrapper"
        wrapper.write_text(f"#!/bin/sh\n/bin/sleep 40 &\necho $! > '{pidfile}'\nwait\n")
        wrapper.chmod(0o755)
        cfg = self.config(timeout=2, cli_paths={"codex": self.fake("codex"), "agy": str(wrapper)})
        start = time.monotonic()
        run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertLess(time.monotonic() - start, 10)
        pid = int(pidfile.read_text())
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_ctrl_c_stops_consult_and_its_judges(self):
        for sig in ("SIGINT", "SIGTERM", "SIGHUP"):
            with self.subTest(signal=sig):
                self._stop_with(sig)

    def test_second_signal_while_judges_ignore_sigterm_still_stops_everything(self):
        start = time.monotonic()
        self._stop_with("SIGINT", stubborn=True, repeats=2)
        self.assertLess(time.monotonic() - start, 8)

    def test_no_stand_in_after_interrupt(self):
        limit = run_module.Verdict("codex", "m", False, "", "usage limit", 0.1, "usage_limit")
        cfg = self.config()
        run_module._STOP.set()
        self.addCleanup(run_module._STOP.clear)
        with mock.patch.object(run_module, "_run_one", return_value=limit) as one:
            verdict = run_module._run_slot(JUDGES["codex"], cfg, "P", str(self.ws), [], self.dir, [],
                                           claim=lambda: FALLBACK)
        self.assertEqual(one.call_count, 1)
        self.assertEqual(verdict.judge, "codex")

    def test_stand_in_removes_the_replaced_judges_stale_failed_file(self):
        from ai_rubric.recovery import resume_consult
        flag = self.dir / "limit"
        body = (f"import os\nif os.path.exists({str(flag)!r}):\n"
                "    sys.stderr.write('You have hit your usage limit.'); sys.exit(1)\n"
                "sys.stderr.write('connection reset'); sys.exit(1)")
        cfg = self.config(cli_paths={"codex": self.fake("codex", body=body), "agy": self.fake("agy")})
        run_dir, _ = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertTrue((run_dir / "codex.md").read_text().startswith("FAILED"))
        flag.touch()
        resume_consult(run_dir, cfg)
        self.assertFalse((run_dir / "codex.md").exists())
        self.assertIn("keep", (run_dir / "neon.md").read_text())
        self.assertIn("keep", (run_dir / "agy.md").read_text())

    def test_folder_taken_between_check_and_create_gets_the_next_name(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        first = make_run_dir(str(self.save), "Same words here", now)
        with mock.patch.object(Path, "exists", return_value=False):  # as if another consult won the race
            second = make_run_dir(str(self.save), "Same words here", now)
        self.assertNotEqual(second, first)
        self.assertTrue(second.is_dir())

    def test_run_folder_is_private(self):
        run_dir = make_run_dir(str(self.save), "Q", datetime(2026, 1, 1))
        self.assertEqual(stat.S_IMODE(run_dir.stat().st_mode), 0o700)

    def test_hangup_ignored_at_start_stays_ignored(self):
        import signal, subprocess
        pids = self.dir / "pids"
        judge = self.dir / "slow-judge"
        judge.write_text(f"#!/bin/sh\necho $$ >> '{pids}'\nexec /bin/sleep 60\n")
        judge.chmod(0o755)
        (self.dir / "brief.md").write_text("Q\n")
        (self.dir / "cfg.toml").write_text(
            f'save_root = "{self.save}"\n[cli]\ncodex = "{judge}"\nagy = "{judge}"\n')
        proc = subprocess.Popen(  # started like nohup: hangups ignored
            [sys.executable, str(Path(__file__).resolve().parents[1] / "bin/consult"),
             "--from", "claude", "--brief", str(self.dir / "brief.md"), "--config", str(self.dir / "cfg.toml")],
            cwd=self.ws, stderr=subprocess.PIPE,
            preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 10
        while (not pids.exists() or len(pids.read_text().split()) < 2) and time.monotonic() < deadline:
            time.sleep(0.1)
        proc.send_signal(signal.SIGHUP)
        time.sleep(1.5)
        self.assertIsNone(proc.poll(), "consult must survive a hangup it was told to ignore")
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=15)

    def _stop_with(self, sig_name, stubborn=False, repeats=1):
        import shutil, signal, subprocess
        shutil.rmtree(self.save, ignore_errors=True)
        pids = self.dir / "pids"
        pids.unlink(missing_ok=True)
        judge = self.dir / "slow-judge"
        trap = 'trap "" TERM HUP\n' if stubborn else ""
        judge.write_text(f"#!/bin/sh\necho $$ >> '{pids}'\n{trap}exec /bin/sleep 60\n")
        judge.chmod(0o755)
        (self.dir / "brief.md").write_text("Q\n")
        (self.dir / "cfg.toml").write_text(
            f'save_root = "{self.save}"\n[cli]\ncodex = "{judge}"\nagy = "{judge}"\n')
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1] / "bin/consult"),
                                 "--from", "claude", "--brief", str(self.dir / "brief.md"),
                                 "--config", str(self.dir / "cfg.toml")],
                                cwd=self.ws, stderr=subprocess.PIPE)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 10
        while (not pids.exists() or len(pids.read_text().split()) < 2) and time.monotonic() < deadline:
            time.sleep(0.1)
        for _ in range(repeats):
            proc.send_signal(getattr(signal, sig_name))
            time.sleep(0.3)
        proc.wait(timeout=15)
        err = proc.stderr.read().decode()
        self.assertIn("cancelled", err)
        time.sleep(0.5)
        for pid in pids.read_text().split():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid), 0)
        run_dir = next(self.save.iterdir())
        self.assertFalse((run_dir / ".run.lock").exists())
        self.assertIn(f"consult --resume {run_dir}", err)

    def test_brief_reaches_every_judge_byte_for_byte(self):
        brief = 'Q: a "b" $c `d` \\n\nline2 \u00fc\u00f1 \u2014 ' + "x" * 50000
        seen = {}
        for name, index in (("codex", -1), ("agy", 1)):
            out = self.dir / f"{name}-prompt.bin"
            seen[name] = out
            body = f"open({str(out)!r}, 'wb').write(args[{index}].encode('utf-8'))"
            setattr(self, f"{name}_cli", self.fake(name, body=body))
        cfg = self.config(cli_paths={"codex": self.codex_cli, "agy": self.agy_cli})
        run_consult("claude", brief, str(self.ws), [], cfg)
        for name, path in seen.items():
            self.assertIn(brief.encode("utf-8"), path.read_bytes(), name)

    def test_nonzero_exit_captures_stderr(self):
        body = "sys.stderr.write('not logged in\\n'); sys.exit(4)"
        cfg = self.config(cli_paths={"codex": self.fake("codex"),
                                     "agy": self.fake("agy", body=body)})
        _, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertFalse(verdicts[1].ok)
        self.assertIn("not logged in", verdicts[1].error)
        self.assertIn("exit 4", verdicts[1].error)

    def test_auth_failure_on_stdout_is_classified_despite_stderr_warning(self):
        body = ("sys.stdout.write('Failed to authenticate: OAuth session expired and could not be refreshed'); "
                "sys.stderr.write('warning: update available'); sys.exit(1)")
        cfg = self.config(cli_paths={"claude": self.fake("claude", body=body),
                                     "agy": self.fake("agy")})
        run_dir, verdicts = run_consult("codex", "Q", str(self.ws), [], cfg)
        self.assertFalse(verdicts[0].ok)
        self.assertEqual(verdicts[0].error_kind, "authentication_required")
        self.assertIn("OAuth session expired", verdicts[0].error)
        self.assertTrue(verdicts[1].ok)
        self.assertIn("keep", (run_dir / "agy.md").read_text())

    def test_usage_limit_brings_in_neon_beside_carbon(self):
        limit = "sys.stderr.write(\"You've hit your usage limit.\"); sys.exit(1)"
        model = "text = args[args.index('--model') + 1]"
        cfg = self.config(cli_paths={"codex": self.fake("codex", body=limit),
                                     "agy": self.fake("agy", body=model)})
        run_dir, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertEqual([(v.judge, v.model, v.ok) for v in verdicts],
                         [("neon", "gemini-4-neon-high", True), ("agy", "gemini-4-carbon-high", True)])
        self.assertEqual(verdicts[0].text, "gemini-4-neon-high")
        self.assertEqual((run_dir / "neon.md").read_text(), "gemini-4-neon-high")
        self.assertIn("usage limit", (run_dir / "run.log").read_text())

    LIMIT = "sys.stderr.write(\"You've hit your usage limit.\"); sys.exit(1)"
    MODEL = "text = args[args.index('--model') + 1]"

    def test_agy_host_gets_claude_and_codex(self):
        cfg = self.config(cli_paths={"claude": self.fake("claude"), "codex": self.fake("codex")})
        _, verdicts = run_consult("agy", "Q", str(self.ws), [], cfg)
        self.assertEqual([(v.judge, v.model, v.ok) for v in verdicts],
                         [("claude", "claude-opus-5-5", True), ("codex", "gpt-6.2-astra", True)])

    def test_agy_host_usage_limit_brings_in_carbon(self):
        cfg = self.config(cli_paths={"claude": self.fake("claude"),
                                     "codex": self.fake("codex", body=self.LIMIT),
                                     "agy": self.fake("agy", body=self.MODEL)})
        run_dir, verdicts = run_consult("agy", "Q", str(self.ws), [], cfg)
        self.assertEqual([(v.judge, v.model, v.ok) for v in verdicts],
                         [("claude", "claude-opus-5-5", True), ("agy", "gemini-4-carbon-high", True)])
        self.assertEqual((run_dir / "agy.md").read_text(), "gemini-4-carbon-high")
        self.assertFalse((run_dir / "codex.md").exists())

    def test_agy_host_both_limited_get_carbon_and_neon(self):
        cfg = self.config(cli_paths={"claude": self.fake("claude", body=self.LIMIT),
                                     "codex": self.fake("codex", body=self.LIMIT),
                                     "agy": self.fake("agy", body=self.MODEL)})
        _, verdicts = run_consult("agy", "Q", str(self.ws), [], cfg)
        self.assertEqual(sorted((v.judge, v.text) for v in verdicts),
                         [("agy", "gemini-4-carbon-high"), ("neon", "gemini-4-neon-high")])

    def test_hanging_pre_run_times_out(self):
        cfg = self.config(pre_run=[sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            run_consult("claude", "Q", str(self.ws), [], cfg)

    def test_agy_resume_after_carbon_held_gives_neon(self):
        from ai_rubric.recovery import resume_consult
        flag = self.dir / "limit"
        claude = (f"import os\nif os.path.exists({str(flag)!r}):\n    " + self.LIMIT +
                  "\nsys.stderr.write('connection reset'); sys.exit(1)")
        cfg = self.config(cli_paths={"claude": self.fake("claude", body=claude),
                                     "codex": self.fake("codex", body=self.LIMIT),
                                     "agy": self.fake("agy", body=self.MODEL)})
        run_dir, verdicts = run_consult("agy", "Q", str(self.ws), [], cfg)
        self.assertEqual([(v.judge, v.ok) for v in verdicts], [("claude", False), ("agy", True)])
        flag.touch()
        _, verdicts = resume_consult(run_dir, cfg)
        self.assertEqual([(v.judge, v.text) for v in verdicts],
                         [("neon", "gemini-4-neon-high"), ("agy", "gemini-4-carbon-high")])
        self.assertFalse((run_dir / "claude.md").exists())

    def test_no_stand_in_left_reports_the_limit(self):
        limit = run_module.Verdict("codex", "m", False, "", "usage limit", 0.1, "usage_limit")
        with mock.patch.object(run_module, "_run_one", return_value=limit) as one:
            verdict = run_module._run_slot(JUDGES["codex"], self.config(), "P", str(self.ws), [],
                                           self.dir, [], claim=lambda: None)
        self.assertEqual(one.call_count, 1)
        self.assertEqual(verdict.error_kind, "usage_limit")

    def test_other_failures_get_no_stand_in(self):
        body = "sys.stderr.write('connection reset'); sys.exit(1)"
        cfg = self.config(cli_paths={"codex": self.fake("codex", body=body), "agy": self.fake("agy")})
        _, verdicts = run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertEqual([v.judge for v in verdicts], ["codex", "agy"])
        self.assertFalse(verdicts[0].ok)

    def test_successful_verdict_discussing_authentication_stays_successful(self):
        cfg = self.config(cli_paths={"claude": self.fake("claude", text="Recommend handling Login expired · Please run /login"),
                                     "agy": self.fake("agy")})
        _, verdicts = run_consult("codex", "Q", str(self.ws), [], cfg)
        self.assertTrue(verdicts[0].ok)
        self.assertIsNone(verdicts[0].error_kind)

    def test_saved_prompt_keeps_carriage_returns_on_initial_run(self):
        seen = self.dir / "prompt.bin"
        body = f"open({str(seen)!r}, 'wb').write(args[1].encode('utf-8'))"
        cfg = self.config(cli_paths={"claude": self.fake("claude", body=body),
                                     "agy": self.fake("agy")})
        run_dir, _ = run_consult("codex", "Question\r\nwith original newlines", str(self.ws), [], cfg)
        self.assertEqual(seen.read_bytes(), (run_dir / "prompt.md").read_bytes())

    def test_pre_run_failure_aborts(self):
        cfg = self.config(pre_run=["/usr/bin/false"], cli_paths={"codex": self.fake("codex"),
                                                         "agy": self.fake("agy")})
        with self.assertRaises(RuntimeError) as cm:
            run_consult("claude", "Q", str(self.ws), [], cfg)
        self.assertIn("false", str(cm.exception))

    def test_missing_pre_run_command_aborts(self):
        cfg = self.config(pre_run=["no-such-precheck"], cli_paths={"codex": self.fake("codex"),
                                                                    "agy": self.fake("agy")})
        with self.assertRaises(RuntimeError):
            run_consult("claude", "Q", str(self.ws), [], cfg)

    def test_roots_deduplicated_and_absolute(self):
        seen = self.dir / "args.txt"
        body = f"open({str(seen)!r}, 'w').write(args[1])"
        other = self.dir / "other"
        other.mkdir()
        cfg = self.config(extra_dirs=[str(other)],
                          cli_paths={"codex": self.fake("codex"), "agy": self.fake("agy", body=body)})
        os.chdir(self.dir)
        self.addCleanup(os.chdir, Path(__file__).resolve().parents[1])
        run_consult("claude", "Q", str(self.ws), ["other", str(self.ws)], cfg)
        prompt = seen.read_text()
        self.assertEqual(prompt.count(f"- {other}\n"), 1)
        self.assertEqual(prompt.count(f"- {self.ws}\n"), 1)


class MakeRunDirTest(unittest.TestCase):
    def test_slug(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = make_run_dir(d, "\n  Is this Plan worth it? yes\nmore",
                                   datetime(2026, 10, 27, 10, 15, 0))
            self.assertEqual(run_dir.name, "20261027-101500-is-this-plan-worth-it-yes")
            self.assertTrue(run_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
