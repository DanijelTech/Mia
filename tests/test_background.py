"""Tests for the background inventory helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core.background import (is_media_url, load_ui_state,  # noqa: E402
                                 parse_window_registry, read_window_registry,
                                 render_window_registry, save_ui_state)


class WindowRegistryTests(unittest.TestCase):
    def test_parses_tab_separated_entries(self):
        items = parse_window_registry(
            "111\thttps://www.youtube.com/watch?v=a\n"
            "222\thttps://example.com\n")
        self.assertEqual(items, [
            {"wid": "111", "url": "https://www.youtube.com/watch?v=a"},
            {"wid": "222", "url": "https://example.com"},
        ])

    def test_ignores_malformed_lines(self):
        items = parse_window_registry(
            "not a window\n"
            "\n"
            "12x\thttps://youtube.com\n"
            "333\t\n"
            "444\thttps://ok.example\n")
        self.assertEqual([i["wid"] for i in items], ["444"])

    def test_round_trip(self):
        items = [{"wid": "7", "url": "https://youtu.be/x"}]
        self.assertEqual(parse_window_registry(render_window_registry(items)), items)

    def test_read_missing_file_is_empty(self):
        self.assertEqual(read_window_registry(Path("/nonexistent/mia-windows")), [])


class MediaUrlTests(unittest.TestCase):
    def test_media_hosts(self):
        for url in ("https://www.youtube.com/watch?v=1", "https://youtu.be/x",
                    "https://open.spotify.com/track/1", "https://soundcloud.com/x"):
            self.assertTrue(is_media_url(url), url)

    def test_other_urls(self):
        for url in ("https://www.google.com/search?q=x", "https://example.com", ""):
            self.assertFalse(is_media_url(url), url)


class UiStateTests(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs" / "ui-state.json"
            self.assertEqual(load_ui_state(path), {})
            save_ui_state(path, {"manual_override": True})
            self.assertTrue(load_ui_state(path)["manual_override"])

    def test_corrupt_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui-state.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_ui_state(path), {})


if __name__ == "__main__":
    unittest.main()
