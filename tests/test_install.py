import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install", ROOT / "install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def found(self):
        with mock.patch.object(install.shutil, "which", return_value=None):
            return dict(install.agents(self.home))

    def test_finds_installed_agents_only(self):
        (self.home / ".claude").mkdir()
        (self.home / ".codex").mkdir()
        self.assertEqual(self.found(), {"Claude Code": self.home / ".claude" / "skills",
                                        "Codex": self.home / ".agents" / "skills"})

    def test_prefers_the_current_antigravity_folder(self):
        (self.home / ".gemini" / "config").mkdir(parents=True)
        (self.home / ".gemini" / "antigravity").mkdir()
        self.assertEqual(self.found(), {"Antigravity": self.home / ".gemini" / "config" / "skills"})

    def test_link_is_idempotent_and_removable(self):
        skills = self.home / ".claude" / "skills"
        self.assertEqual(install.link(skills), "linked")
        self.assertEqual(Path(install.os.path.realpath(skills / install.NAME)), install.SKILL_DIR)
        self.assertEqual(install.link(skills), "already linked")
        self.assertEqual(install.unlink(skills), "removed")
        self.assertFalse((skills / install.NAME).exists())
        self.assertTrue((install.SKILL_DIR / "SKILL.md").exists())

    def test_never_replaces_an_existing_folder(self):
        skills = self.home / ".claude" / "skills"
        (skills / install.NAME).mkdir(parents=True)
        self.assertTrue(install.link(skills).startswith("skipped"))
        self.assertEqual(install.unlink(skills), "nothing to remove")
        self.assertTrue((skills / install.NAME).is_dir())


if __name__ == "__main__":
    unittest.main()
