"""Bilingual deterministic replies: English must never get Slovenian answers."""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core import i18n  # noqa: E402
from mia_core.integration import (  # noqa: E402
    detect_feedback, detect_remember, google_request, media_stop_request,
    music_play_request, time_answer, weather_request,
)


class LocalizeTests(unittest.TestCase):
    def setUp(self):
        i18n.set_lang("sl")

    def tearDown(self):
        i18n.set_lang("sl")

    def test_exact_sentence(self):
        self.assertEqual(i18n.localize("Narejeno.", "en"), "Done.")
        self.assertEqual(i18n.localize("Narejeno.", "sl"), "Narejeno.")

    def test_dynamic_sentence(self):
        self.assertEqual(i18n.localize("Glasnost 40, šefe.", "en"),
                         "Volume 40, boss.")
        self.assertEqual(
            i18n.localize("Mapa /tmp/x je pripravljena.", "en"),
            "Folder /tmp/x is ready.")

    def test_confirmation_prompt(self):
        self.assertEqual(
            i18n.localize("Naj trajno izbrišem /tmp/x? Potrdi s »ja«.", "en"),
            "Should I permanently delete /tmp/x? Confirm with yes.")

    def test_unknown_is_not_mangled(self):
        text = "To je povsem novo besedilo."
        self.assertEqual(i18n.localize(text, "en"), text)

    def test_help_is_translated(self):
        from mia_core.autonomy.intents import route_help
        english = i18n.localize(route_help(), "en")
        self.assertIn("I understand commands", english)

    def test_catalog(self):
        self.assertEqual(i18n.t("media.stopped", "en"),
                         "I stopped the music, boss.")
        self.assertEqual(i18n.t("media.stopped", "sl"),
                         "Ustavila sem glasbo, šefe.")
        self.assertEqual(i18n.t("volume.set", "en", value="40%"),
                         "Volume 40%, boss.")

    def test_env_language(self):
        i18n.set_lang("en")
        self.assertEqual(i18n.current_lang(), "en")
        self.assertEqual(i18n.localize("Nič ne igra, šefe."),
                         "Nothing is playing, boss.")

    def test_health_messages(self):
        self.assertEqual(i18n.localize("45% (na bateriji)", "en"),
                         "45% (on battery)")
        self.assertEqual(
            i18n.localize("Pozor, šefe: ocena 92 od 100. Ni aktivne omrežne povezave",
                          "en"),
            "Attention, boss: score 92 of 100. No active network connection")


class TimeAnswerTests(unittest.TestCase):
    NOW = dt.datetime(2026, 11, 27, 19, 5)

    def test_slovenian(self):
        self.assertEqual(time_answer("koliko je ura", self.NOW),
                         "Ura je 19 in 5.")

    def test_english(self):
        self.assertEqual(time_answer("what time is it", self.NOW, lang="en"),
                         "It is seven oh five in the evening.")
        self.assertEqual(
            time_answer("what day is it", self.NOW, lang="en"),
            "Today is Friday, November 27, 2026.")

    def test_english_both(self):
        answer = time_answer("what is the date and time", self.NOW, lang="en")
        self.assertIn("Friday", answer)
        self.assertIn("seven oh five in the evening", answer)


class EnglishIntentTests(unittest.TestCase):
    def test_english_music(self):
        self.assertEqual(music_play_request("play some music"), "")
        self.assertEqual(music_play_request("play Bohemian Rhapsody on youtube"),
                         "bohemian rhapsody")
        self.assertEqual(music_play_request("youtube play Bajaga"), "bajaga")

    def test_english_stop(self):
        self.assertTrue(media_stop_request("stop the music"))
        self.assertTrue(media_stop_request("close all youtube windows"))
        self.assertFalse(media_stop_request("what is the weather"))

    def test_english_google(self):
        mode, query = google_request("search on google for the capital of France")
        self.assertEqual(mode, "answer")
        self.assertEqual(query, "capital of france")
        mode, query = google_request("show me on google python asyncio")
        self.assertEqual(mode, "show")

    def test_english_weather(self):
        self.assertEqual(weather_request("what is the weather in London"),
                         "london")

    def test_english_feedback_and_remember(self):
        self.assertEqual(detect_feedback("that was right")["verdict"], "positive")
        self.assertEqual(detect_feedback("that was wrong")["verdict"], "negative")
        self.assertTrue(detect_remember("remember this procedure"))


if __name__ == "__main__":
    unittest.main()
