"""Tests for the weather and Google command parsers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core.integration import google_request, weather_request  # noqa: E402


class WeatherRequestTests(unittest.TestCase):
    def test_weather_without_city_uses_default(self):
        for text in ("Kakšno je vreme?", "Kakšno bo vreme jutri?",
                     "Povej mi vreme.", "Kakšna je napoved za jutri?"):
            self.assertEqual(weather_request(text), "", text)

    def test_weather_with_city(self):
        self.assertEqual(weather_request("Kakšno je vreme v Mariboru?"), "mariboru")
        self.assertEqual(weather_request("Povej mi vreme za Ljubljano."), "ljubljano")
        self.assertEqual(weather_request("Kakšna je temperatura v Kopru?"), "kopru")
        self.assertEqual(weather_request("Kakšno je vreme v Novem mestu?"),
                         "novem mestu")

    def test_small_talk_about_weather_is_not_a_weather_query(self):
        self.assertIsNone(weather_request("Kaj misliš o vremenu?"))
        self.assertIsNone(weather_request("Vreme je danes lepo."))


class GoogleRequestTests(unittest.TestCase):
    def test_open_google_without_query(self):
        self.assertEqual(google_request("Odpri Google."), ("show", ""))

    def test_search_on_google_answers_aloud(self):
        self.assertEqual(google_request("Poišči na Googlu kavo."),
                         ("answer", "kavo"))

    def test_open_google_and_search_opens_browser(self):
        self.assertEqual(google_request("Odpri Google in poišči kavo."),
                         ("show", "kavo"))

    def test_ask_on_google_uses_answer_mode(self):
        mode, query = google_request("Povej mi na Googlu kdo je Tesla.")
        self.assertEqual(mode, "answer")
        self.assertIn("tesla", query)

    def test_non_google_is_ignored(self):
        self.assertEqual(google_request("Kako si?"), (None, ""))


if __name__ == "__main__":
    unittest.main()
