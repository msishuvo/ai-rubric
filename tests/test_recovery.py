import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_rubric import discover, run as runner
from ai_rubric.config import Config
from ai_rubric.run import run_consult
from ai_rubric.recovery import load_run, resume_consult


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws = self.root / "work space"
        self.ws.mkdir()
        self.other = self.root / "extra space"
        self.other.mkdir()
        self.cfg = Config(save_root=str(self.root / "save"))
        self.calls = self.root / "calls.jsonl"
        self.expired = self.root / "expired"
        self.expired.touch()
        for patch in (mock.patch.dict(os.environ, {"PATH": str(self.root / "empty")}),
                      mock.patch.dict(discover.KNOWN_LOCATIONS, {"agy": [], "claude": [], "codex": []})):
            patch.start()
            self.addCleanup(patch.stop)
        for name in ("claude", "agy"):
            path = self.root / name
            path.write_text(f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
with open({str(self.calls)!r}, "a") as f:
    f.write(json.dumps({{"name": {name!r}, "cwd": os.getcwd(), "args": sys.argv[1:]}}) + "\\n")
if {name!r} == "claude" and sys.argv[1:] == ["auth", "login", "--claudeai"]:
    Path({str(self.expired)!r}).unlink(missing_ok=True)
    sys.exit(0)
if {name!r} == "claude" and sys.argv[1:] == ["auth", "status", "--json"]:
    print(json.dumps({{"loggedIn": True, "authMethod": "claude.ai"}}))
    sys.exit(0)
if {name!r} == "claude" and Path({str(self.expired)!r}).exists():
    sys.stderr.write("Login expired · Please run /login")
    sys.exit(1)
print("## Verdict\\nkeep " + {name!r})
''')
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
            self.cfg.cli_paths[name] = str(path)

    def initial(self):
        return run_consult("codex", 'Q: "quotes" $literal `text`\nü',
                           str(self.ws), [str(self.other)], self.cfg)

    def read_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_resume_only_failed_judge_preserves_verdict_and_exact_context(self):
        run_dir, _ = self.initial()
        agy = run_dir / "agy.md"
        before = (agy.read_bytes(), agy.stat().st_mtime_ns)
        prompt = (run_dir / "prompt.md").read_bytes()
        self.expired.unlink()
        self.cfg.extra_dirs = ["/must/not/replace/saved/roots"]
        resumed_dir, verdicts = resume_consult(run_dir, self.cfg)
        self.assertEqual(resumed_dir, run_dir)
        self.assertTrue(all(v.ok for v in verdicts))
        self.assertEqual((agy.read_bytes(), agy.stat().st_mtime_ns), before)
        calls = self.read_calls()
        self.assertEqual([c["name"] for c in calls].count("agy"), 1)
        retried = calls[-1]
        self.assertEqual(retried["name"], "claude")
        self.assertTrue(Path(retried["cwd"]).samefile(self.ws))
        self.assertEqual(retried["args"][1].encode(), prompt)
        self.assertEqual(retried["args"][-2:], ["--add-dir", str(self.other)])
        self.assertIn("Login expired", (run_dir / "run.log").read_text())
        self.assertTrue(all(v["ok"] for v in load_run(run_dir)["verdicts"]))

    def test_expired_resume_attempts_once_and_retains_successful_result(self):
        run_dir, _ = self.initial()
        _, verdicts = resume_consult(run_dir, self.cfg)
        self.assertFalse(verdicts[0].ok)
        self.assertEqual(verdicts[0].error_kind, "authentication_required")
        self.assertTrue(verdicts[1].ok)
        self.assertEqual(len(self.read_calls()), 3)

    def test_resume_all_successful_is_a_noop(self):
        self.expired.unlink()
        run_dir, _ = self.initial()
        resume_consult(run_dir, self.cfg)
        self.assertEqual(len(self.read_calls()), 2)

    def test_missing_or_corrupt_manifest_does_not_invoke_a_judge(self):
        run_dir, _ = self.initial()
        path = run_dir / "run.json"
        original = json.loads(path.read_text())
        variants = ["not json", json.dumps({}), json.dumps({**original, "version": 99}),
                    json.dumps({**original, "cwd": "relative"}),
                    json.dumps({**original, "extra_dirs": [None]}),
                    json.dumps({**original, "verdicts": []})]
        changed_model = json.loads(path.read_text())
        changed_model["verdicts"][0]["model"] = "substitute-model"
        variants.append(json.dumps(changed_model))
        unexpected_field = json.loads(path.read_text())
        unexpected_field["verdicts"][0]["unexpected"] = True
        variants.append(json.dumps(unexpected_field))
        wrong_judge_auth = json.loads(path.read_text())
        wrong_judge_auth["verdicts"][1].update(ok=False, text="", error="boom",
                                              error_kind="authentication_required")
        variants.append(json.dumps(wrong_judge_auth))
        for value in variants:
            with self.subTest(value=value):
                path.write_text(value)
                with self.assertRaisesRegex(RuntimeError, "saved run|manifest"):
                    resume_consult(run_dir, self.cfg)
                self.assertEqual(len(self.read_calls()), 2)
        path.unlink()
        with self.assertRaisesRegex(RuntimeError, "saved run|manifest"):
            resume_consult(run_dir, self.cfg)

    def test_missing_original_folder_refuses_resume(self):
        run_dir, _ = self.initial()
        self.other.rmdir()
        with self.assertRaisesRegex(RuntimeError, "workspace folder"):
            resume_consult(run_dir, self.cfg)
        self.assertEqual(len(self.read_calls()), 2)

    def test_oversized_manifest_numbers_report_cli_error_without_changing_results(self):
        run_dir, _ = self.initial()
        manifest = run_dir / "run.json"
        original = manifest.read_text()
        saved = {name: (run_dir / f"{name}.md").read_bytes() for name in ("claude", "agy")}
        script = Path(__file__).resolve().parents[1] / "bin" / "consult"
        for field in ("started_at", "claude.seconds", "agy.seconds"):
            with self.subTest(field=field):
                state = json.loads(original)
                if field == "started_at":
                    state["started_at"] = 10 ** 400
                else:
                    index = 0 if field == "claude.seconds" else 1
                    state["verdicts"][index]["seconds"] = 10 ** 400
                manifest.write_text(json.dumps(state))
                before = manifest.read_bytes()
                result = subprocess.run(
                    [sys.executable, str(script), "--resume", str(run_dir),
                     "--config", str(self.root / "no-config.toml")],
                    cwd=self.ws, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Cannot resume saved run", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(manifest.read_bytes(), before)
                for name, content in saved.items():
                    self.assertEqual((run_dir / f"{name}.md").read_bytes(), content)
                self.assertEqual(len(self.read_calls()), 2)
                self.assertFalse((run_dir / ".run.lock").exists())

    def test_active_resume_lock_refuses_duplicate_invocation(self):
        run_dir, _ = self.initial()
        (run_dir / ".run.lock").touch()
        with self.assertRaisesRegex(RuntimeError, "already running"):
            resume_consult(run_dir, self.cfg)
        self.assertEqual(len(self.read_calls()), 2)

    def test_result_is_checkpointed_before_another_judge_finishes(self):
        real = runner._run_one
        from threading import Event
        fast_saved = Event()

        def judge(*args):
            if args[0].name == "claude":
                if not fast_saved.wait(5):
                    raise AssertionError("other result was never checkpointed")
            return real(*args)

        # Observe the public on-disk checkpoint while the other fake judge is pending.
        import ai_rubric.recovery as recovery
        write = recovery.save_run

        def checkpoint(path, state):
            write(path, state)
            loaded = json.loads((path / "run.json").read_text())
            if any(v["judge"] == "agy" and v["ok"] for v in loaded["verdicts"]):
                fast_saved.set()

        with mock.patch.object(runner, "_run_one", side_effect=judge), \
                mock.patch.object(recovery, "save_run", side_effect=checkpoint):
            run_dir, verdicts = self.initial()
        self.assertTrue(fast_saved.is_set())
        self.assertTrue(verdicts[1].ok)
        self.assertTrue((run_dir / "agy.md").is_file())
        self.assertFalse((run_dir / ".run.lock").exists())

    def test_stale_last_message_cannot_be_used_as_retried_verdict(self):
        run_dir, _ = self.initial()
        (run_dir / ".claude-last-message.md").write_text("STALE verdict")
        self.expired.unlink()
        _, verdicts = resume_consult(run_dir, self.cfg)
        self.assertEqual(verdicts[0].text, "## Verdict\nkeep claude\n")
        self.assertFalse((run_dir / ".claude-last-message.md").exists())

    def test_resume_pre_run_failure_does_not_touch_saved_results(self):
        run_dir, _ = self.initial()
        original = (run_dir / "run.json").read_bytes()
        self.cfg.pre_run = ["/usr/bin/false"]
        with self.assertRaisesRegex(RuntimeError, "pre_run"):
            resume_consult(run_dir, self.cfg)
        self.assertEqual((run_dir / "run.json").read_bytes(), original)
        self.assertEqual(len(self.read_calls()), 2)

    def test_explicit_interactive_login_is_followed_by_failed_judge_retry(self):
        run_dir, _ = self.initial()
        with mock.patch.object(sys, "stdin") as incoming, mock.patch.object(sys, "stdout") as outgoing:
            incoming.isatty.return_value = outgoing.isatty.return_value = True
            _, verdicts = resume_consult(run_dir, self.cfg, login=True)
        self.assertTrue(all(v.ok for v in verdicts))
        calls = self.read_calls()
        self.assertEqual(calls[2]["args"], ["auth", "login", "--claudeai"])
        self.assertEqual(calls[3]["args"], ["auth", "status", "--json"])
        self.assertEqual(calls[4]["name"], "claude")
        self.assertEqual(len(calls), 5)

    def test_login_without_auth_failure_does_not_start_a_login_flow(self):
        self.expired.unlink()
        run_dir, _ = self.initial()
        with self.assertRaisesRegex(RuntimeError, "no failed Claude sign-in"):
            resume_consult(run_dir, self.cfg, login=True)
        self.assertEqual(len(self.read_calls()), 2)

    def test_unattended_login_keeps_manifest_and_successful_verdict(self):
        run_dir, _ = self.initial()
        before = (run_dir / "run.json").read_bytes()
        with mock.patch.object(sys, "stdin") as incoming:
            incoming.isatty.return_value = False
            with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                resume_consult(run_dir, self.cfg, login=True)
        self.assertEqual((run_dir / "run.json").read_bytes(), before)
        self.assertIn("keep agy", (run_dir / "agy.md").read_text())
        self.assertEqual(len(self.read_calls()), 2)

    def test_cli_round_trip_uses_saved_context_and_preserves_partial_progress(self):
        script = Path(__file__).resolve().parents[1] / "bin" / "consult"
        brief = self.root / "brief.md"
        brief.write_text("Is this proposal sound?")
        config = self.root / "custom config.toml"
        config.write_text(f'save_root = {json.dumps(self.cfg.save_root)}\n[cli]\n' +
                          "".join(f'{name} = {json.dumps(path)}\n' for name, path in self.cfg.cli_paths.items()))

        def command(*args):
            return subprocess.run([sys.executable, str(script), *args, "--config", str(config)],
                                  cwd=self.ws, capture_output=True, text=True, timeout=10)

        initial = command("--from", "codex", "--brief", str(brief), "--add-dir", str(self.other))
        self.assertEqual(initial.returncode, 0, initial.stderr)
        self.assertIn("PARTIAL: 1 of 2", initial.stdout)
        saved = next(line.removeprefix("Saved: ") for line in initial.stdout.splitlines() if line.startswith("Saved: "))
        run_dir = Path(saved)
        before = (run_dir / "agy.md").read_bytes()
        background = command("--resume", saved, "--login")
        self.assertEqual(background.returncode, 2)
        self.assertIn("interactive terminal", background.stderr)
        self.assertEqual(len(self.read_calls()), 2)
        self.expired.unlink()
        resumed = command("--resume", saved)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("live workspace", resumed.stdout)
        self.assertNotIn("PARTIAL:", resumed.stdout)
        self.assertEqual((run_dir / "agy.md").read_bytes(), before)
        self.assertEqual(len(self.read_calls()), 3)

    def test_checkpoint_failure_never_exports_an_uncommitted_success(self):
        import ai_rubric.recovery as recovery
        run_dir, _ = self.initial()
        original = (run_dir / "claude.md").read_bytes()
        self.expired.unlink()
        save = recovery.save_run

        def interrupted(path, state):
            if state["verdicts"][0]["ok"]:
                raise OSError("interrupted checkpoint")
            save(path, state)

        with mock.patch.object(recovery, "save_run", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "interrupted checkpoint"):
                resume_consult(run_dir, self.cfg)
        self.assertFalse(load_run(run_dir)["verdicts"][0]["ok"])
        self.assertEqual((run_dir / "claude.md").read_bytes(), original)
        self.assertIn("keep agy", (run_dir / "agy.md").read_text())

    def test_committed_results_repair_missing_or_stale_exports_without_retry(self):
        run_dir, _ = self.initial()
        self.expired.unlink()
        _, verdicts = resume_consult(run_dir, self.cfg)
        expected = verdicts[0].text.encode()
        (run_dir / "claude.md").write_text("FAILED: stale export")
        (run_dir / "agy.md").unlink()
        self.expired.touch()  # Any accidental retry now fails.
        _, resumed = resume_consult(run_dir, self.cfg)
        self.assertTrue(all(v.ok for v in resumed))
        self.assertEqual((run_dir / "claude.md").read_bytes(), expected)
        self.assertIn("keep agy", (run_dir / "agy.md").read_text())
        self.assertEqual(len(self.read_calls()), 3)


if __name__ == "__main__":
    unittest.main()
