"""Tests for the text→viseme timeline used by the 3D avatar."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import avatar_visemes  # noqa: E402
import avatar_config  # noqa: E402

AVATAR_DIR = ROOT / "server" / "hud" / "avatar"


def _node_facts():
    """Import the pure avatar modules with node and return their metadata."""
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for name in ("characters.js", "motion.js", "presets.js"):
            shutil.copy(AVATAR_DIR / name, tmpdir / name)
        (tmpdir / "package.json").write_text('{"type":"module"}')
        script = """
import { CHARACTERS } from './characters.js';
import { ACTIONS, resolveAction, samplePose } from './motion.js';
import {
  DEFAULTS, SCHEMA, HAIR_STYLES, ACCESSORY_STYLES, PRESETS,
} from './presets.js';
const actions = {};
for (const [id, a] of Object.entries(ACTIONS)) {
  actions[id] = {
    label: a.label, dur: a.dur, group: a.group,
    keys: a.keys.map((k) => k.t),
    start: samplePose(a, 0), end: samplePose(a, 1),
  };
}
const aliases = {};
for (const name of ['pomahaj', 'prekloni', 'prikimi', 'brcni', 'boks',
  'blokiraj', 'pokloni', 'skeniraj']) aliases[name] = resolveAction(name);
const schemaKeys = SCHEMA.flatMap((g) => g.controls.map((c) => c.key));
console.log(JSON.stringify({
  characters: CHARACTERS,
  actions,
  aliases,
  defaults: Object.keys(DEFAULTS),
  schemaKeys,
  hair: Object.keys(HAIR_STYLES),
  accessories: Object.keys(ACCESSORY_STYLES),
  presets: Object.keys(PRESETS),
}));
"""
        (tmpdir / "facts.mjs").write_text(script)
        proc = subprocess.run([node, str(tmpdir / "facts.mjs")], cwd=tmpdir,
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr or proc.stdout)
        return json.loads(proc.stdout)



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

    def test_every_default_has_a_validator(self):
        known = (avatar_config.COLOR_KEYS | avatar_config.BOOL_KEYS
                 | avatar_config.STRING_KEYS | set(avatar_config.RANGES))
        self.assertEqual(set(avatar_config.DEFAULTS), known)

    def test_character_and_wardrobe_settings_validate(self):
        cfg = avatar_config.sanitize({
            "character": "nova", "accessory": "armor",
            "accessoryColor": "#00E5FF", "robot": True,
            "robotGlow": "#ff00aa", "garmentLength": 9,
            "robotIntensity": -2, "actionSpeed": 9,
        })
        self.assertEqual(cfg["character"], "nova")
        self.assertEqual(cfg["accessory"], "armor")
        self.assertEqual(cfg["accessoryColor"], "#00e5ff")
        self.assertEqual(cfg["robotGlow"], "#ff00aa")
        self.assertTrue(cfg["robot"])
        self.assertEqual(cfg["garmentLength"], 1.2)
        self.assertEqual(cfg["robotIntensity"], 0.0)
        self.assertEqual(cfg["actionSpeed"], 2.0)

    def test_bad_new_types_are_rejected(self):
        with self.assertRaises(ValueError):
            avatar_config.sanitize({"robot": "true"})
        with self.assertRaises(ValueError):
            avatar_config.sanitize({"accessoryColor": "cyan"})


class AvatarMotionAndCharacterTests(unittest.TestCase):
    """The procedural motion, character roster and wig catalog."""

    @classmethod
    def setUpClass(cls):
        cls.facts = _node_facts()

    def test_character_roster_has_several_women(self):
        characters = self.facts["characters"]
        self.assertGreaterEqual(len(characters), 8)
        for cid, character in characters.items():
            self.assertIn("label", character, cid)
            unknown = set(character) - set(self.facts["defaults"]) - {"label", "note"}
            self.assertFalse(unknown, f"{cid} has unknown keys {unknown}")
        self.assertIn("nova", characters)
        self.assertTrue(characters["nova"].get("robot"))

    def test_required_moves_exist(self):
        actions = self.facts["actions"]
        for name in ("wave", "nod", "shake", "bend", "bow",
                     "punch", "kick", "block", "kata", "combat"):
            self.assertIn(name, actions)
            self.assertTrue(actions[name]["label"])
            self.assertGreater(actions[name]["dur"], 0)
            self.assertEqual(actions[name]["keys"][0], 0)
            self.assertEqual(actions[name]["keys"][-1], 1)

    def test_actions_start_and_end_at_rest(self):
        for name, action in self.facts["actions"].items():
            for edge in ("start", "end"):
                values = [abs(v) for pose in action[edge].values()
                          for v in pose.values()]
                self.assertTrue(all(v < 1e-9 for v in values),
                                f"{name}.{edge} does not return to rest")

    def test_slovenian_aliases_resolve(self):
        aliases = self.facts["aliases"]
        self.assertEqual(aliases["pomahaj"], "wave")
        self.assertEqual(aliases["prekloni"], "bend")
        self.assertEqual(aliases["prikimi"], "nod")
        self.assertEqual(aliases["brcni"], "kick")
        self.assertEqual(aliases["boks"], "punch")
        self.assertEqual(aliases["blokiraj"], "block")
        self.assertEqual(aliases["pokloni"], "bow")
        self.assertEqual(aliases["skeniraj"], "scan")

    def test_hair_and_accessory_catalog(self):
        hair = set(self.facts["hair"])
        self.assertLessEqual({"long", "short", "bob", "pixie", "ponytail",
                              "bun", "twin", "braid", "afro", "mohawk"}, hair)
        accessories = set(self.facts["accessories"])
        self.assertLessEqual({"none", "armor", "visor", "dress", "skirt",
                              "antenna", "headset"}, accessories)

    def test_character_presets_are_wired_into_the_schema(self):
        self.assertIn("character", self.facts["presets"])
        self.assertIn("character", self.facts["schemaKeys"])
        self.assertIn("accessory", self.facts["schemaKeys"])
        self.assertIn("actionSpeed", self.facts["schemaKeys"])

    def test_avatar_runtime_imports_the_new_modules(self):
        runtime = (AVATAR_DIR / "avatar.js").read_text()
        for module in ("hair.js", "garments.js", "motion.js"):
            self.assertIn(module, runtime)
        page = (ROOT / "server/hud/avatar.html").read_text()
        self.assertIn("gestureChips", page)
        self.assertIn("HAIR_STYLES", page)

    def test_hidden_layers_keep_their_limb_meshes(self):
        runtime = (AVATAR_DIR / "avatar.js").read_text()
        wardrobe = runtime.split("_applyWardrobe() {", 1)[1].split("_tintKind", 1)[0]
        self.assertIn("_setBare", wardrobe)
        self.assertNotIn("_setVisible('top', this.config.top", runtime)
        self.assertNotIn("_setVisible('bottom', this.config.bottom", runtime)
        bare = runtime.split("_setBare(mesh, bare) {", 1)[1].split("_applyWardrobe", 1)[0]
        self.assertIn("map = null", bare)
        self.assertIn("__clothed", bare)


class AvatarRenderLoopTests(unittest.TestCase):
    """Regression guards for the idle-loop snap and the render budget."""

    @classmethod
    def setUpClass(cls):
        cls.runtime = (AVATAR_DIR / "avatar.js").read_text()
        cls.hud = (ROOT / "server/hud/index.html").read_text()

    def test_idle_clip_is_rotation_only(self):
        block = self.runtime.split("async loadIdle()", 1)[1].split("_firstMorphMesh", 1)[0]
        self.assertIn("endsWith('.quaternion')", block)
        self.assertIn("clip.tracks = clip.tracks.filter", block)

    def test_pose_reset_restores_last_mixer_output(self):
        update = self.runtime.split("update(dt, now) {", 1)[1]
        self.assertIn("this._restoreBase();", update)
        self.assertIn("this._cacheBase();", update)
        self.assertNotIn("this._resetRest();", update)
        restore = self.runtime.split("_restoreBase() {", 1)[1].split("_cacheBase()", 1)[0]
        self.assertIn("_basePose", restore)
        self.assertNotIn("_restPose", restore)

    def test_quality_scale_scales_the_backing_store(self):
        resize = self.runtime.split("resize() {", 1)[1].split("applyConfig(", 1)[0]
        self.assertIn("qualityScale", resize)

    def test_reactor_throttles_behind_the_avatar(self):
        self.assertIn("avatar-ready", self.hud)
        self.assertIn("reactorLast", self.hud)
        self.assertIn("RDPR", self.hud)


if __name__ == "__main__":
    unittest.main()
