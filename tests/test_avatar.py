"""Tests for the text→viseme timeline used by the 3D avatar."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import avatar_visemes  # noqa: E402
import avatar_config  # noqa: E402


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
        presets = (ROOT / "server/hud/avatar/presets.js").read_text()
        config = (ROOT / "server/avatar_config.py").read_text()
        for name in ("mia-female.glb", "mia-female-idle.glb"):
            self.assertIn(name, presets)
            self.assertIn(name, config)
            self.assertIn(name, script)

    def test_hud_loads_the_avatar_layer(self):
        hud = (ROOT / "server/hud/index.html").read_text()
        self.assertIn('id="avatar"', hud)
        self.assertIn("/hud/avatar/avatar.js", hud)
        page = (ROOT / "server/hud/avatar.html").read_text()
        self.assertIn("/hud/avatar/avatar.js", page)
        self.assertIn("/hud/avatar/presets.js", page)
        self.assertIn("hairStyle", page)
        self.assertIn("randomize", page)


class AvatarSettingsContractTests(unittest.TestCase):
    """JS presets, the Python validator and the control deck stay in sync."""

    @classmethod
    def setUpClass(cls):
        cls.presets = (ROOT / "server/hud/avatar/presets.js").read_text()
        block = re.search(r"export const DEFAULTS = \{(.*?)\n\};", cls.presets, re.S)
        cls.js_defaults = set(re.findall(r"([A-Za-z0-9_]+)\s*:", block.group(1)))
        schema = re.search(r"export const SCHEMA = \[(.*)\n\];", cls.presets, re.S)
        cls.schema_block = schema.group(1)
        cls.schema_keys = set(re.findall(r"key: '([A-Za-z0-9_]+)'", cls.schema_block))

    def test_defaults_match_the_python_validator(self):
        self.assertTrue(self.js_defaults)
        self.assertEqual(self.js_defaults, set(avatar_config.DEFAULTS))

    def test_every_control_is_a_known_setting(self):
        self.assertTrue(self.schema_keys)
        self.assertLessEqual(self.schema_keys, self.js_defaults)

    def test_schema_ranges_match_the_server_clamps(self):
        found = {}
        pattern = (r"\{ key: '([A-Za-z0-9_]+)', type: 'range'[^}]*"
                   r"min: (-?[\d.]+), max: (-?[\d.]+)")
        for key, low, high in re.findall(pattern, self.schema_block):
            found[key] = (float(low), float(high))
        self.assertEqual(found, avatar_config.RANGES)

    def test_settings_count_covers_every_control(self):
        self.assertIn("export const SETTINGS_COUNT = Object.keys(DEFAULTS).length;",
                      self.presets)
        self.assertGreaterEqual(len(self.js_defaults), 60)


class AvatarConfigValidationTests(unittest.TestCase):
    def test_empty_patch_returns_defaults(self):
        self.assertEqual(avatar_config.sanitize({}), avatar_config.DEFAULTS)

    def test_numbers_are_clamped(self):
        cfg = avatar_config.sanitize({"height": 9, "cameraFov": -5})
        self.assertEqual(cfg["height"], 1.35)
        self.assertEqual(cfg["cameraFov"], 18.0)

    def test_fps_cap_is_an_integer(self):
        cfg = avatar_config.sanitize({"fpsCap": 59.6})
        self.assertIsInstance(cfg["fpsCap"], int)
        self.assertEqual(cfg["fpsCap"], 60)

    def test_bad_color_is_rejected(self):
        with self.assertRaises(ValueError):
            avatar_config.sanitize({"hairColor": "red"})

    def test_wrong_type_is_rejected(self):
        with self.assertRaises(ValueError):
            avatar_config.sanitize({"hair": "true"})
        with self.assertRaises(ValueError):
            avatar_config.sanitize({"height": True})

    def test_unknown_keys_are_ignored(self):
        cfg = avatar_config.sanitize({"notASetting": 1})
        self.assertNotIn("notASetting", cfg)

    def test_merge_drops_unknown_stored_keys(self):
        cfg = avatar_config.merge({"hairColor": "#000000", "legacy": 1})
        self.assertEqual(cfg["hairColor"], "#000000")
        self.assertNotIn("legacy", cfg)


if __name__ == "__main__":
    unittest.main()
