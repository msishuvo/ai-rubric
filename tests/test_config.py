import tempfile
import unittest
from pathlib import Path

from ai_rubric.config import load_config


class LoadConfigTest(unittest.TestCase):
    def test_missing_config_gives_defaults(self):
        cfg = load_config(Path("/nonexistent/ai-rubric/config.toml"))
        self.assertEqual(cfg.timeout, 1200)
        self.assertTrue(cfg.save_root.endswith(".local/state/ai-rubric/consultations"))
        self.assertEqual(cfg.extra_dirs, [])
        self.assertEqual(cfg.cli_paths, {})
        self.assertIsNone(cfg.pre_run)

    def test_config_values_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "config.toml")
            p.write_text('timeout = 60\nextra_dirs = ["~/x"]\npre_run = ["true"]\n'
                         '[cli]\ncodex = "/tmp/fake"\n')
            cfg = load_config(p)
        self.assertEqual(cfg.timeout, 60)
        self.assertEqual(cfg.extra_dirs, [str(Path.home() / "x")])
        self.assertEqual(cfg.cli_paths, {"codex": "/tmp/fake"})
        self.assertEqual(cfg.pre_run, ["true"])

    def test_model_key_rejected(self):
        for text in ('model = "x"\n', '[cli]\neffort = "high"\n'):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d, "config.toml")
                p.write_text(text)
                with self.assertRaises(ValueError) as cm:
                    load_config(p)
                self.assertIn("pinned", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
