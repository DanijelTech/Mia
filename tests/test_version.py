"""One version everywhere: VERSION, mia_core, scripts and changelog."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import mia_core  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_version_file_is_semver(self):
        value = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(value, r"^\d+\.\d+\.\d+$")

    def test_mia_core_matches_version_file(self):
        value = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(mia_core.__version__, value)

    def test_changelog_mentions_the_release(self):
        value = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"[{value}]", changelog)

    def test_scripts_support_version(self):
        for name in ("install.sh", "uninstall.sh", "update.sh",
                     "start-mia.sh", "stop-mia.sh", "build-package.sh"):
            with self.subTest(script=name):
                result = subprocess.run(
                    ["bash", str(ROOT / name), "--version"],
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertRegex(result.stdout, r"^Mia \d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
