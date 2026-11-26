import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_rubric.blocks import remove_block, upsert_block

REPO = Path(__file__).resolve().parents[1]
MD = ("<!-- ai-rubric start -->", "<!-- ai-rubric end -->")


class BlocksTest(unittest.TestCase):
    def test_upsert_into_empty(self):
        self.assertEqual(upsert_block("", "body", *MD), f"{MD[0]}\nbody\n{MD[1]}\n")

    def test_upsert_appends_after_blank_line(self):
        out = upsert_block("# Mine\nkeep\n", "body", *MD)
        self.assertEqual(out, f"# Mine\nkeep\n\n{MD[0]}\nbody\n{MD[1]}\n")

    def test_upsert_replaces_in_place(self):
        once = upsert_block("a\n", "old", *MD) + "tail\n"
        twice = upsert_block(once, "new", *MD)
        self.assertEqual(twice, f"a\n\n{MD[0]}\nnew\n{MD[1]}\ntail\n")

    def test_remove_restores_original(self):
        for original in ("", "# Mine\nkeep\n", "no newline"):
            installed = upsert_block(original, "body", *MD)
            self.assertEqual(remove_block(installed, *MD),
                             original if original.endswith("\n") or not original else original + "\n")


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_failed_write_leaves_original_and_no_temp_file(self):
        from unittest import mock
        from ai_rubric import blocks
        f = self.dir / "CLAUDE.md"
        f.write_text("precious\n")
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                blocks.write_atomic(f, "new\n")
        self.assertEqual(f.read_text(), "precious\n")
        self.assertEqual([p.name for p in self.dir.iterdir()], ["CLAUDE.md"])

    def test_symlinked_file_stays_a_link_and_keeps_its_mode(self):
        from ai_rubric import blocks
        real = self.dir / "dotfiles" / "CLAUDE.md"
        real.parent.mkdir()
        real.write_text("old\n")
        real.chmod(0o640)
        link = self.dir / "CLAUDE.md"
        link.symlink_to(real)
        blocks.write_atomic(link, "new\n")
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_text(), "new\n")
        self.assertEqual(real.stat().st_mode & 0o777, 0o640)

    def test_new_file_is_readable_like_a_normal_file(self):
        from ai_rubric import blocks
        f = self.dir / "AGENTS.md"
        blocks.write_atomic(f, "x\n")
        self.assertEqual(f.stat().st_mode & 0o777, 0o644)


class BlocksFileTest(unittest.TestCase):
    def test_crlf_file_round_trips_byte_for_byte(self):
        import sys
        from ai_rubric import blocks
        with tempfile.TemporaryDirectory() as d:
            f, frag = Path(d, "CLAUDE.md"), Path(d, "frag.md")
            original = "# Mine\r\nkeep \u00f8\r\n".encode("utf-8")
            f.write_bytes(original)
            frag.write_text("body\n")
            blocks.main(["upsert", str(f), "md", str(frag)])
            installed = f.read_bytes()
            self.assertNotIn(b"\n<!--", installed.replace(b"\r\n", b""))
            blocks.main(["remove", str(f), "md"])
            self.assertEqual(f.read_bytes(), original)

    def test_check_rejects_unclosed_marker(self):
        from ai_rubric import blocks
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "CLAUDE.md")
            f.write_text("x\n<!-- ai-rubric start -->\nhalf\n")
            self.assertEqual(blocks.main(["check", str(f), "md"]), 1)
            f.write_text("x\n")
            self.assertEqual(blocks.main(["check", str(f), "md"]), 0)


class InstallScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name, "home")
        self.home.mkdir()
        self.repo = REPO

    def run_install(self, *args, repo=None):
        env = {**os.environ, "HOME": str(self.home)}
        return subprocess.run(["bash", str((repo or self.repo) / "install.sh"), *args],
                              capture_output=True, text=True, env=env)

    def snapshot(self):
        return {str(p.relative_to(self.home)): (os.readlink(p) if p.is_symlink() else p.read_bytes())
                for p in sorted(self.home.rglob("*")) if p.is_symlink() or p.is_file()}

    def test_install_creates_links_and_blocks(self):
        proc = self.run_install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for link, target in ((".claude/skills/consult", "skills/consult"),
                             (".codex/skills/consult", "skills/consult"),
                             (".local/bin/consult", "bin/consult")):
            p = self.home / link
            self.assertTrue(p.is_symlink(), link)
            self.assertEqual(os.readlink(p), str(self.repo / target))
        for f in (".claude/CLAUDE.md", ".codex/AGENTS.md", ".gemini/GEMINI.md"):
            text = (self.home / f).read_text()
            self.assertEqual(text.count("<!-- ai-rubric start -->"), 1, f)
        rules = (self.home / ".codex/rules/default.rules").read_text()
        self.assertIn('prefix_rule(pattern=["consult"], decision="allow")', rules)
        self.assertIn("# ai-rubric start", rules)
        for name in ("claude", "codex", "agy"):
            self.assertIn(name, proc.stdout)
        import json
        agy = json.loads((self.home / ".gemini/antigravity-cli/settings.json").read_text())
        self.assertIn("command(cat)", agy["permissions"]["allow"])
        saved = Path((self.home / ".local/state/ai-rubric/python").read_text().strip())
        self.assertTrue(saved.is_absolute() and os.access(saved, os.X_OK))

    def test_antigravity_gets_the_skill_and_the_consult_rule(self):
        proc = self.run_install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        plugin = self.home / ".gemini/config/plugins/ai-rubric"
        self.assertTrue(plugin.is_symlink())
        self.assertEqual(os.readlink(plugin), str(self.repo / "install/antigravity-plugin"))
        self.assertEqual((plugin / "skills/consult/SKILL.md").resolve(),
                         (self.repo / "skills/consult/SKILL.md").resolve())
        self.assertTrue((plugin / "plugin.json").is_file())
        text = (self.home / ".gemini/GEMINI.md").read_text()
        self.assertIn("## When judging (ai-rubric)", text)
        self.assertIn("## Second opinions (ai-rubric)", text)
        self.run_install("--uninstall")
        self.assertFalse(plugin.is_symlink())
        self.assertFalse((self.home / ".gemini/GEMINI.md").read_text().strip())

    def test_plugin_version_matches_the_tool(self):
        import json
        from ai_rubric import __version__
        plugin = json.loads((self.repo / "install/antigravity-plugin/plugin.json").read_text())
        self.assertEqual(plugin["version"], __version__)

    def test_foreign_plugin_link_left_alone(self):
        plugin = self.home / ".gemini/config/plugins/ai-rubric"
        plugin.parent.mkdir(parents=True)
        plugin.symlink_to("/somewhere/else")
        proc = self.run_install()
        self.assertIn("left alone", proc.stdout)
        self.assertEqual(os.readlink(plugin), "/somewhere/else")
        self.run_install("--uninstall")
        self.assertTrue(plugin.is_symlink())

    def test_install_twice_is_idempotent(self):
        self.run_install()
        first = self.snapshot()
        proc = self.run_install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.snapshot(), first)

    def test_existing_content_preserved(self):
        (self.home / ".claude").mkdir()
        mine = self.home / ".claude/CLAUDE.md"
        mine.write_text("# Mine\nkeep\n")
        (self.home / ".codex/rules").mkdir(parents=True)
        rules = self.home / ".codex/rules/default.rules"
        rules.write_text('prefix_rule(pattern=["ls"], decision="allow")\n')
        self.run_install()
        self.assertTrue(mine.read_text().startswith("# Mine\nkeep\n"))
        self.assertTrue(rules.read_text().startswith('prefix_rule(pattern=["ls"], decision="allow")\n'))
        proc = self.run_install("--uninstall")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(mine.read_text(), "# Mine\nkeep\n")
        self.assertEqual(rules.read_text(), 'prefix_rule(pattern=["ls"], decision="allow")\n')
        self.assertFalse((self.home / ".claude/skills/consult").exists())
        self.assertFalse((self.home / ".local/bin/consult").is_symlink())
        import json
        agy = json.loads((self.home / ".gemini/antigravity-cli/settings.json").read_text())
        self.assertNotIn("permissions", agy)

    def test_block_replaced_not_duplicated(self):
        copy = Path(self.tmp.name, "repo")
        shutil.copytree(self.repo, copy, ignore=shutil.ignore_patterns(".git", ".superpowers", "__pycache__"))
        self.run_install(repo=copy)
        (copy / "install/claude-rule.md").write_text("NEW RULE TEXT\n")
        self.run_install(repo=copy)
        text = (self.home / ".claude/CLAUDE.md").read_text()
        self.assertEqual(text.count("<!-- ai-rubric start -->"), 1)
        self.assertIn("NEW RULE TEXT", text)

    def test_real_file_at_link_target_not_overwritten(self):
        target = self.home / ".local/bin/consult"
        target.parent.mkdir(parents=True)
        target.write_text("mine")
        proc = self.run_install()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(target.read_text(), "mine")
        self.assertIn("left alone", proc.stdout + proc.stderr)

    def test_old_python_aborts_before_any_change(self):
        shim = Path(self.tmp.name, "oldpy")
        shim.mkdir()
        (shim / "python3").write_text("#!/bin/sh\nexit 1\n")
        (shim / "python3").chmod(0o755)
        env = {**os.environ, "HOME": str(self.home), "PATH": f"{shim}:/usr/bin:/bin"}
        proc = subprocess.run(["bash", str(self.repo / "install.sh")], capture_output=True,
                              text=True, env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("3.11", proc.stdout + proc.stderr)
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_broken_marker_aborts_before_any_change(self):
        (self.home / ".claude").mkdir()
        (self.home / ".claude/CLAUDE.md").write_text("<!-- ai-rubric start -->\nhalf\n")
        proc = self.run_install()
        self.assertEqual(proc.returncode, 2)
        self.assertFalse((self.home / ".claude/skills").exists())
        self.assertFalse((self.home / ".local").exists())

    def test_unreadable_antigravity_settings_abort_before_any_change(self):
        settings = self.home / ".gemini/antigravity-cli/settings.json"
        settings.parent.mkdir(parents=True)
        for broken in ('{ // comment\n"x": 1 }', '["not", "an", "object"]'):
            with self.subTest(broken=broken):
                settings.write_text(broken)
                before = self.snapshot()
                proc = self.run_install()
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("nothing was changed", proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertEqual(self.snapshot(), before)

    def test_uninstall_still_removes_everything_else_when_antigravity_settings_are_broken(self):
        self.assertEqual(self.run_install().returncode, 0)
        settings = self.home / ".gemini/antigravity-cli/settings.json"
        settings.write_text('{ // comment\n"x": 1 }')
        proc = self.run_install("--uninstall")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn(str(settings), proc.stderr)
        self.assertFalse((self.home / ".claude/skills/consult").exists())
        self.assertNotIn("ai-rubric", (self.home / ".claude/CLAUDE.md").read_text())
        self.assertEqual(settings.read_text(), '{ // comment\n"x": 1 }')

    def test_uninstall_leaves_foreign_symlinks(self):
        self.run_install()
        foreign = self.home / ".claude/skills/other"
        foreign.symlink_to("/somewhere/else")
        self.run_install("--uninstall")
        self.assertTrue(foreign.is_symlink())


if __name__ == "__main__":
    unittest.main()
