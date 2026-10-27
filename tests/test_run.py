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
