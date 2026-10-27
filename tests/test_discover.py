import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_rubric import discover
from ai_rubric.config import Config
from ai_rubric.discover import find_cli


def make_exe(path: Path) -> str:
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class FindCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.empty_path = mock.patch.dict(os.environ, {"PATH": str(self.dir / "nothing")})
        self.no_known = mock.patch.dict(discover.KNOWN_LOCATIONS, {"agy": [], "codex": [], "claude": []})
        self.empty_path.start()
        self.no_known.start()

    def tearDown(self):
        self.no_known.stop()
        self.empty_path.stop()
        self.tmp.cleanup()

    def test_find_cli_prefers_config_path(self):
        exe = make_exe(self.dir / "my-codex")
        bindir = self.dir / "bin"
        bindir.mkdir()
        make_exe(bindir / "codex")
        with mock.patch.dict(os.environ, {"PATH": str(bindir)}):
            self.assertEqual(find_cli("codex", Config(cli_paths={"codex": exe})), exe)

    def test_find_cli_falls_back_to_path(self):
        bindir = self.dir / "bin"
        bindir.mkdir()
        exe = make_exe(bindir / "agy")
        with mock.patch.dict(os.environ, {"PATH": str(bindir)}):
            self.assertEqual(find_cli("agy", Config()), exe)

    def test_find_cli_known_location(self):
        exe = make_exe(self.dir / "codex")
        with mock.patch.dict(discover.KNOWN_LOCATIONS, {"codex": [exe]}):
            self.assertEqual(find_cli("codex", Config()), exe)

    def test_find_cli_missing_returns_none(self):
        self.assertIsNone(find_cli("claude", Config()))

    def test_non_executable_config_path_skipped(self):
        plain = self.dir / "codex.txt"
        plain.write_text("not a program")
        self.assertIsNone(find_cli("codex", Config(cli_paths={"codex": str(plain)})))



class KnownLocationsTest(unittest.TestCase):
    def test_known_locations_cover_owner_mac(self):
        home = str(Path.home())
        self.assertIn(f"{home}/.local/bin/codex", discover.KNOWN_LOCATIONS["codex"])
        self.assertEqual(discover.KNOWN_LOCATIONS["codex"][-1],
                         "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")


if __name__ == "__main__":
    unittest.main()
