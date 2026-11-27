"""Tests for media stop/play parsing and for closing Mia's media windows."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core.config import find_tool  # noqa: E402
from mia_core.integration import media_stop_request, music_play_request  # noqa: E402

MIA_CLOSE = ROOT / "skills" / "mia-companion" / "bin" / "mia-close"

XDOTOOL_STUB = """#!/bin/sh
case "$1" in
  windowclose) echo "closed $2" >> "$STUB_CLOSED"; [ "$2" = "999" ] && exit 1; exit 0;;
  getwindowname)
    case "$2" in
      111) echo "Pesem - YouTube";;
      222) echo "Terminal";;
      333) echo "Mia HUD - Firefox";;
      *) exit 1;;
    esac;;
  getwindowclassname)
    case "$2" in
      111) echo "Google-chrome";;
      222) echo "Gnome-terminal";;
      333) echo "firefox";;
      *) exit 1;;
    esac;;
  search) printf "111\\n222\\n333\\n";;
esac
exit 0
"""


class MediaStopTests(unittest.TestCase):
    def test_stop_commands(self):
        for text in (
            "Mia, ustavi youtube!",
            "ustavi youtube",
            "zapri vsa okna youtube",
            "zapri youtube",
            "ustavi glasbo",
            "ugasni glasbo",
            "dovolj glasbe",
            "prekini predvajanje",
            "ustavi",
            "stop",
            "počisti zaslon",
            "umakni z zaslona",
            "ugasni panel",
        ):
            self.assertTrue(media_stop_request(text), text)

    def test_not_a_stop_command(self):
        for text in (
            "pusti glasbo",
            "pusti muziko na youtube",
            "zamenjaj glasbo",
            "pavziraj",
            "zapri vsa okna",
            "ustavi proces nginx",
            "zapri brskalnik",
            "kaj misliš o youtube",
            "kakšno je vreme",
        ):
            self.assertFalse(media_stop_request(text), text)

    def test_stop_phrases_are_not_play_requests(self):
        for text in ("ustavi youtube", "zapri vsa okna youtube",
                     "ustavi glasbo", "dovolj glasbe", "ugasni glasbo"):
            self.assertIsNone(music_play_request(text), text)

    def test_play_requests_still_work(self):
        self.assertEqual(music_play_request("pusti glasbo"), "")
        self.assertEqual(music_play_request("pusti muziko na youtube"), "")
        self.assertEqual(music_play_request("zamenjaj glasbo"), "")
        self.assertEqual(music_play_request("druga pesem"), "")
        self.assertEqual(music_play_request("youtube pusti muziko"), "")
        self.assertEqual(music_play_request("predvajaj Bajago"), "bajago")
        self.assertEqual(music_play_request("poišči na youtube Bajaga"), "bajaga")

    def test_music_word_alone_is_not_a_play_request(self):
        self.assertIsNone(music_play_request("kaj misliš o youtube"))
        self.assertIsNone(music_play_request("youtube je danes počasen"))


class FindToolTests(unittest.TestCase):
    def test_repo_copy_is_found_without_path(self):
        # The systemd unit does not inherit ~/.local/bin; the repo copy must win.
        self.assertTrue(find_tool("mia-close"))
        self.assertTrue(find_tool("mia-open"))
        self.assertIsNone(find_tool("mia-definitely-not-a-tool"))


class MiaCloseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / ".cache").mkdir()
        (self.home / "bin").mkdir()
        stub = self.home / "bin" / "xdotool"
        stub.write_text(XDOTOOL_STUB, encoding="utf-8")
        stub.chmod(0o755)
        self.closed = self.home / "closed.log"
        self.registry = self.home / ".cache" / "mia-windows"

    def close(self, *patterns: str) -> str:
        env = {
            "HOME": str(self.home),
            "PATH": f"{self.home / 'bin'}:/usr/bin:/bin",
            "XDG_STATE_HOME": str(self.home / "state"),
            "STUB_CLOSED": str(self.closed),
        }
        result = subprocess.run(["sh", str(MIA_CLOSE), *patterns],
                                capture_output=True, text=True, env=env,
                                timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def closed_ids(self) -> list[str]:
        if not self.closed.exists():
            return []
        return [line.split()[-1] for line in
                self.closed.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_closes_only_matching_registered_windows(self):
        self.registry.write_text(
            "111\thttps://www.youtube.com/watch?v=a\n"
            "222\thttps://example.com\n", encoding="utf-8")
        out = self.close("youtube", "youtu.be")
        self.assertIn("closed: https://www.youtube.com/watch?v=a", out)
        self.assertEqual(self.closed_ids(), ["111"])
        self.assertEqual(self.registry.read_text(encoding="utf-8"),
                         "222\thttps://example.com\n")

    def test_keeps_a_window_whose_close_failed(self):
        self.registry.write_text(
            "999\thttps://www.youtube.com/watch?v=z\n", encoding="utf-8")
        self.close("youtube")
        self.assertIn("999\thttps://www.youtube.com/watch?v=z",
                      self.registry.read_text(encoding="utf-8"))

    def test_falls_back_to_window_titles_for_unregistered_windows(self):
        self.registry.write_text("", encoding="utf-8")
        out = self.close("youtube")
        self.assertIn("okno 111", out)
        # the terminal and the HUD window must survive
        self.assertEqual(self.closed_ids(), ["111"])


if __name__ == "__main__":
    unittest.main()
