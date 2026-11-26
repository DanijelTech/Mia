"""Tests for the text→viseme timeline used by the 3D avatar."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import avatar_visemes  # noqa: E402


class AvatarVisemeTests(unittest.TestCase):
    def test_timeline_is_monotonic_and_covers_duration(self):
        timeline = avatar_visemes.timeline("Dober dan, kako si?", 1800)
        self.assertTrue(timeline["visemes"])
        self.assertEqual(len(timeline["visemes"]), len(timeline["times"]))
        self.assertEqual(len(timeline["visemes"]), len(timeline["durations"]))
        self.assertEqual(timeline["times"][0], 0)
        for a, b in zip(timeline["times"], timeline["times"][1:]):
            self.assertLessEqual(a, b)
        end = timeline["times"][-1] + timeline["durations"][-1]
        self.assertGreaterEqual(end, 1700)
        self.assertLessEqual(end, 1900)

    def test_slovenian_phonemes_map_to_oculus_set(self):
        timeline = avatar_visemes.timeline("Mia, dober dan. Kako si?", 2000)
        self.assertTrue(set(timeline["visemes"]).issubset(set(avatar_visemes.VISEMES)))
        joined = " ".join(timeline["visemes"])
        self.assertIn("DD", joined)   # d
        self.assertIn("aa", joined)   # a
        self.assertIn("SS", joined)   # s
        self.assertIn("sil", joined)  # spaces / punctuation

    def test_empty_and_punctuation_are_safe(self):
        empty = avatar_visemes.timeline("", 500)
        self.assertEqual(empty["visemes"], ["sil"])
        punctuation = avatar_visemes.timeline("...", 600)
        self.assertTrue(punctuation["visemes"])
        self.assertTrue(all(v == "sil" for v in punctuation["visemes"]))

    def test_tags_are_removed_and_mood_is_extracted(self):
        clean, tags = avatar_visemes.strip_tags(
            "[mood:veselo] Dober dan, šefe! [gesture:wave]")
        self.assertNotIn("[mood", clean)
        self.assertNotIn("[gesture", clean)
        self.assertIn("dober dan", clean.lower())
        self.assertEqual(tags.get("mood"), "veselo")
        self.assertEqual(tags.get("gesture"), "wave")
        timeline = avatar_visemes.timeline(
            "[mood:veselo] Dober dan, šefe! [gesture:wave]", 1000)
        self.assertEqual(timeline["mood"], "happy")
        self.assertEqual(timeline["gesture"], "wave")

    def test_pcm_duration_is_used(self):
        pcm = b"\x00\x01" * 16000  # 1 second @ 16 kHz
        timeline = avatar_visemes.timeline_for_pcm("Dober dan.", pcm)
        self.assertGreaterEqual(timeline["duration_ms"], 950)
        self.assertLessEqual(timeline["duration_ms"], 1100)

    def test_long_text_has_more_visemes(self):
        short = avatar_visemes.timeline("Da.", 800)
        long = avatar_visemes.timeline(
            "To je daljši stavek, ki mora imeti bistveno več visemov.", 3000)
        self.assertGreater(len(long["visemes"]), len(short["visemes"]))


if __name__ == "__main__":
    unittest.main()
