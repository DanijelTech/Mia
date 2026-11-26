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

    def test_pcm_timeline_keeps_tags_for_mood_gesture_look(self):
        pcm = b"\x00\x01" * 8000  # 0.5 s @ 16 kHz
        timeline = avatar_visemes.timeline_for_pcm(
            "[mood:žalostno] Žal mi je. [gesture:bow] [look:down]", pcm)
        self.assertEqual(timeline["mood"], "sad")
        self.assertEqual(timeline["gesture"], "bow")
        self.assertEqual(timeline["look"], "down")
        self.assertGreaterEqual(timeline["duration_ms"], 450)

    def test_timeline_without_tags_has_empty_gesture_and_look(self):
        timeline = avatar_visemes.timeline("Dober dan.", 900)
        self.assertEqual(timeline["mood"], "neutral")
        self.assertEqual(timeline["gesture"], "")
        self.assertEqual(timeline["look"], "")

    def test_long_text_has_more_visemes(self):
        short = avatar_visemes.timeline("Da.", 800)
        long = avatar_visemes.timeline(
            "To je daljši stavek, ki mora imeti bistveno več visemov.", 3000)
        self.assertGreater(len(long["visemes"]), len(short["visemes"]))


class AvatarAssetContractTests(unittest.TestCase):
    """The HUD, the server defaults and the fetch script must agree."""

    def test_default_model_files_are_fetched(self):
        script = (ROOT / "server/scripts/fetch-avatar-assets.sh").read_text()
        js = (ROOT / "server/hud/avatar/avatar.js").read_text()
        server = (ROOT / "server/server.py").read_text()
        for name in ("mia-female.glb", "mia-female-idle.glb"):
            self.assertIn(name, js)
            self.assertIn(name, server)
            self.assertIn(name, script)

    def test_hud_loads_the_avatar_layer(self):
        hud = (ROOT / "server/hud/index.html").read_text()
        self.assertIn('id="avatar"', hud)
        self.assertIn("/hud/avatar/avatar.js", hud)
        page = (ROOT / "server/hud/avatar.html").read_text()
        self.assertIn("/hud/avatar/avatar.js", page)
        self.assertIn("hairStyle", page)


if __name__ == "__main__":
    unittest.main()
