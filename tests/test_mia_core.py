"""Tests for the stdlib-only Mia learning/knowledge core."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core import privacy
from mia_core.cli import main as cli_main
from mia_core.config import load_config
from mia_core.context import build_brief
from mia_core.db import Store
from mia_core.habits import mine_habits
from mia_core.integration import (detect_feedback, detect_intent, detect_remember,
                                  episode_payload, outcome_from_turn)
from mia_core.knowledge import (scan_skill_tree, search_skills, tree_payload,
                                validate_tree)
from mia_core.learning import LearningCore
from mia_core.recipes import (match_anti_patterns, match_recipes, normalize,
                              recipe_key, record_feedback)


class TempStoreMixin:
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "learning.db"
        self.store = Store(self.db)
        self.cfg = load_config(overrides={
            "db_path": str(self.db),
            "context": {"max_chars": 1200},
            "habits": {"min_evidence": 3},
        })

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def episode(self, **overrides):
        payload = {
            "request": "odpri mi google in poisci vreme",
            "response": "Odprla sem.",
            "source": "voice",
            "intent": "open",
            "outcome": "success",
            "tools": ["mia-ctl"],
            "steps": [{"action": "mia-ctl", "args": ["open", "https://google.com"]}],
            "tags": ["voice", "open"],
            "meta": {"entities": [{"kind": "domain", "value": "google.com"}],
                     "app": "google"},
            "ts": time.time(),
        }
        payload.update(overrides)
        return self.store.record_episode(**payload)


class PrivacyTests(unittest.TestCase):
    def test_redacts_tokens_passwords_and_emails(self):
        text = ("API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456 password: hunter2 "
                "mail me at user@example.com")
        out = privacy.redact(text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", out)
        self.assertNotIn("hunter2", out)
        self.assertNotIn("user@example.com", out)
        self.assertIn("[REDACTED]", out)

    def test_clip(self):
        self.assertEqual(privacy.clip("abcdef", 4), "abc…")
        self.assertEqual(privacy.clip("abc", 10), "abc")


class StoreTests(TempStoreMixin, unittest.TestCase):
    def test_episode_roundtrip_and_stats(self):
        ep_id = self.episode()
        self.assertGreater(ep_id, 0)
        episode = self.store.get_episode(ep_id)
        self.assertEqual(episode["intent"], "open")
        self.assertEqual(episode["steps"][0]["action"], "mia-ctl")
        stats = self.store.stats()
        self.assertEqual(stats["episodes"], 1)
        self.assertEqual(stats["recipes"], 0)  # raw Store does not learn
        from mia_core.recipes import learn_from_episode
        # unverified success must NOT become a trusted recipe
        self.assertFalse(learn_from_episode(self.store, episode)["learned"])
        self.assertEqual(self.store.stats()["recipes"], 0)
        self.store.update_episode(ep_id, verified=1, verification_status="verified",
                                  verification={"status": "verified",
                                                "method": "test"})
        episode = self.store.get_episode(ep_id)
        self.assertTrue(learn_from_episode(self.store, episode)["learned"])
        self.assertEqual(self.store.stats()["recipes"], 1)
        self.assertIn("success", stats["outcomes"])

    def test_secrets_are_redacted_before_storage(self):
        ep_id = self.store.record_episode(
            request="moj kljuc je sk-abcdefghijklmnopqrstuvwxyz123456",
            source="cli", outcome="success")
        episode = self.store.get_episode(ep_id)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", episode["request"])
        self.assertIn("[REDACTED]", episode["request"])

    def test_search(self):
        self.episode(request="odpri mi google")
        results = self.store.search("google")
        self.assertTrue(results)
        self.assertEqual(results[0]["kind"], "episode")

    def test_export_import(self):
        self.episode()
        data = self.store.export_data()
        self.assertEqual(data["format"], "mia-learning")
        other = Store(Path(self.tmp.name) / "other.db")
        try:
            imported = other.import_data(data)
            self.assertGreater(imported.get("episodes", 0), 0)
            self.assertEqual(other.stats()["episodes"], 1)
        finally:
            other.close()

    def test_upsert_recipe_confidence(self):
        self.store.upsert_recipe("k", title="t", steps=[{"action": "x"}], success=1)
        rec = self.store.get_recipe_by_key("k")
        first = rec["confidence"]
        self.store.upsert_recipe("k", success=1)
        rec = self.store.get_recipe_by_key("k")
        self.assertGreaterEqual(rec["confidence"], first)
        self.assertEqual(rec["success_count"], 2)


class RecipeTests(TempStoreMixin, unittest.TestCase):
    def test_normalize_and_key(self):
        self.assertEqual(normalize("Odpri mi Google!"), ["odpri", "google"])
        self.assertEqual(recipe_key("Google, odpri mi"), "google-odpri")

    def test_match_recipes(self):
        self.store.upsert_recipe(
            recipe_key("odpri google"), title="odpri google",
            steps=[{"action": "mia-ctl", "args": ["open", "https://google.com"]}],
            success=3)
        matches = match_recipes(self.store, "odpri mi google", threshold=0.4)
        self.assertTrue(matches)
        self.assertGreater(matches[0]["score"], 0.5)

    def test_positive_feedback_promotes_recipe(self):
        ep_id = self.episode()
        result = record_feedback(self.store, ep_id, "positive", "tako je")
        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "positive")
        self.assertTrue(self.store.get_recipe_by_key(recipe_key(
            "odpri mi google in poisci vreme")))

    def test_negative_feedback_creates_anti_pattern(self):
        ep_id = self.episode()
        result = record_feedback(self.store, ep_id, "negative",
                                 "ne tako, uporabi mia-close")
        self.assertTrue(result["ok"])
        patterns = self.store.list_anti_patterns()
        self.assertTrue(patterns)
        self.assertIn("mia-close", patterns[0]["cause"])
        self.assertEqual(self.store.get_episode(ep_id)["outcome"], "failure")

    def test_feedback_preserves_recipe_steps(self):
        ep_id = self.episode()
        result = record_feedback(self.store, ep_id, "positive", "tako je")
        self.assertTrue(result["ok"])
        recipe = self.store.get_recipe_by_key(recipe_key(
            "odpri mi google in poisci vreme"))
        self.assertTrue(recipe["steps"])
        self.assertEqual(recipe["steps"][0]["action"], "mia-ctl")

    def test_failed_verification_creates_mistake(self):
        from mia_core.recipes import learn_from_episode
        ep_id = self.episode()
        self.store.update_episode(ep_id, verification_status="failed", verified=0)
        episode = self.store.get_episode(ep_id)
        result = learn_from_episode(self.store, episode)
        self.assertTrue(result["learned"])
        self.assertEqual(result["kind"], "mistake")

    def test_anti_pattern_match(self):
        self.store.upsert_anti_pattern(
            "ap:zapri", symptom="okno se ne zapre s pkill",
            cause="Chrome posreduje okna", fix="uporabi mia-close")
        matches = match_anti_patterns(self.store, "zapri okno s pkill", threshold=0.3)
        self.assertTrue(matches)


class HabitTests(TempStoreMixin, unittest.TestCase):
    def test_mines_entity_preference_and_time_routine(self):
        now = time.time()
        for i in range(4):
            self.store.record_episode(
                request="odpri mi google", response="ok", source="voice",
                intent="open", outcome="success",
                tags=["voice"], meta={"entities": [{"kind": "domain",
                                                    "value": "google.com"}]},
                ts=now - i * 3600)
        result = mine_habits(self.store, self.cfg, apply=True)
        self.assertGreaterEqual(len(result["candidates"]), 1)
        habits = self.store.list_habits()
        self.assertTrue(any("google.com" in h["subject"] for h in habits))
        self.assertTrue(all(h["confidence"] > 0 for h in habits))

    def test_sequence_habit(self):
        now = time.time()
        for i in range(4):
            self.store.record_episode(request="pusti mi glasbo", response="ok",
                                      source="voice", intent="music",
                                      outcome="success", ts=now - i * 600)
            self.store.record_episode(request="pojacaj glasnost", response="ok",
                                      source="voice", intent="volume",
                                      outcome="success", ts=now - i * 600 + 60)
        result = mine_habits(self.store, self.cfg, apply=True)
        self.assertTrue(any(c["kind"] == "routine" for c in result["candidates"]))

    def test_min_evidence_prevents_noise(self):
        self.store.record_episode(request="enkrat", source="voice", outcome="success",
                                  meta={"entities": [{"kind": "app", "value": "x"}]})
        result = mine_habits(self.store, self.cfg, apply=True)
        self.assertEqual(result["candidates"], [])


class ContextTests(TempStoreMixin, unittest.TestCase):
    def test_brief_contains_recipe_and_mistake_and_respects_limit(self):
        self.store.upsert_recipe(
            recipe_key("odpri google"), title="odpri google",
            steps=[{"action": "mia-ctl", "args": ["open", "https://google.com"]}],
            success=4)
        self.store.upsert_anti_pattern(
            "ap:1", symptom="odpri google s pkill", cause="napačno orodje",
            fix="mia-ctl open https://google.com")
        text = build_brief(self.store, self.cfg, "odpri google")
        self.assertIn("MIA SPOMIN", text)
        self.assertIn("Preverjeni postopki", text)
        self.assertIn("NE ponavljaj", text)
        self.assertLessEqual(len(text), 1200)

    def test_brief_disabled(self):
        cfg = dict(self.cfg)
        cfg["context"] = {**cfg["context"], "enabled": False}
        self.assertEqual(build_brief(self.store, cfg, "x"), "")


class IntegrationTests(unittest.TestCase):
    def test_detect_feedback(self):
        self.assertEqual(detect_feedback("tako je")["verdict"], "positive")
        self.assertEqual(detect_feedback("To je bilo prav.")["verdict"], "positive")
        neg = detect_feedback("ne tako, raje odpri v Chromu")
        self.assertEqual(neg["verdict"], "negative")
        self.assertIn("odpri v chromu", neg["note"])
        self.assertIsNone(detect_feedback("odpri mi google in poišči vreme ter mi povej kaj bo jutri"))

    def test_detect_remember(self):
        self.assertTrue(detect_remember("zapomni si postopek")["remember"])
        self.assertIsNone(detect_remember("zapomni si, da imam sestanek jutri ob osmih zjutraj in da moram pripraviti poročilo"))

    def test_intent(self):
        self.assertEqual(detect_intent("pusti mi glasbo"), "music")
        self.assertEqual(detect_intent("pojačaj glasnost"), "volume")
        self.assertEqual(detect_intent("zapri okno"), "close")

    def test_entities(self):
        from mia_core.integration import extract_entities
        self.assertIn({"kind": "app", "value": "google"},
                      extract_entities("odpri mi google in poisci vreme"))
        self.assertIn({"kind": "query", "value": "vreme"},
                      extract_entities("odpri mi google in poisci vreme"))
        self.assertIn({"kind": "artist", "value": "baja mali knindza"},
                      extract_entities("pusti mi Baja Mali Knindza"))
        self.assertEqual(extract_entities("zapri okno"), [])

    def test_outcome(self):
        self.assertEqual(outcome_from_turn("ok"), "success")
        self.assertEqual(outcome_from_turn("", ["boom"]), "failure")
        self.assertEqual(outcome_from_turn("ok", interrupted=True), "partial")
        self.assertEqual(outcome_from_turn("ok", ["ignored: wake"]), "success")

    def test_episode_payload(self):
        class Timing:
            transcript = "odpri google"
            response_text = "ok"
            tools_used = ["mia-ctl"]
            errors = []
            interrupted = False
            run_id = "r1"
            stt_model = "tiny"
            llm_model = "local"
            tts_model = "piper"
            end_of_speech_monotonic = 1.0
            total_done_monotonic = 3.5

        payload = episode_payload(Timing(), "mia-main", "odpri google")
        self.assertEqual(payload["source"], "voice")
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["duration_s"], 2.5)
        self.assertEqual(payload["meta"]["run_id"], "r1")


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "skills"

    def test_tree_is_valid(self):
        report = validate_tree(self.root)
        self.assertTrue(report["ok"], report["errors"])
        payload = tree_payload(self.root)
        self.assertGreaterEqual(payload["summary"]["skills"], 7)
        self.assertEqual(payload["summary"]["errors"], 0)
        names = {n["name"] for n in payload["flat"]}
        for expected in ("mia-companion", "mia-desktop", "mia-learning",
                         "mia-music", "mia-browser", "mia-productivity",
                         "mia-diagnostics"):
            self.assertIn(expected, names)

    def test_parent_child_links(self):
        nodes = {n["name"]: n for n in scan_skill_tree(self.root)}
        self.assertEqual(nodes["mia-desktop"]["parent"], "mia-companion")
        self.assertEqual(nodes["mia-learning"]["parent"], "mia-companion")
        self.assertIn("references/control-cookbook.md",
                      nodes["mia-desktop"]["references"])
        self.assertEqual(nodes["mia-desktop"]["missing_references"], [])

    def test_search(self):
        results = search_skills(self.root, "windows")
        self.assertTrue(results)
        self.assertEqual(results[0]["name"], "mia-desktop")

    def test_no_missing_references_anywhere(self):
        for node in scan_skill_tree(self.root):
            self.assertEqual(node["missing_references"], [],
                             f"{node['name']} references missing files")


class CliTests(unittest.TestCase):
    def test_record_brief_and_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "l.db")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--db", db, "--json", "record",
                               "--request", "odpri google",
                               "--response", "ok",
                               "--outcome", "success",
                               "--tool", "mia-ctl"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["ok"])
            self.assertGreater(payload["episode_id"], 0)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--db", db, "--json", "feedback",
                               "--episode", str(payload["episode_id"]),
                               "--verdict", "positive", "--note", "tako je"])
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads(buf.getvalue())["ok"])

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--db", db, "--json", "brief", "odpri google"])
            self.assertEqual(rc, 0)
            brief = json.loads(buf.getvalue())
            self.assertIn("MIA SPOMIN", brief["text"])

    def test_doctor_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--db", str(Path(tmp) / "l.db"), "--json", "doctor"])
            self.assertEqual(rc, 0)
            report = json.loads(buf.getvalue())
            self.assertTrue(report["tree"]["ok"])


class LearningCoreTests(unittest.TestCase):
    def test_disabled_is_silent(self):
        core = LearningCore({"learning": {"enabled": False}},
                            path=Path(tempfile.mkdtemp()) / "l.db")
        self.assertIsNone(core.record_turn({}, "s", "hello"))
        self.assertEqual(core.brief("x"), "")
        core.close()

    def test_record_and_mine(self):
        tmp = tempfile.mkdtemp()
        core = LearningCore({"learning": {"db_path": str(Path(tmp) / "l.db"),
                                          "habits": {"min_evidence": 2}}})
        for _ in range(3):
            core.record_episode({"request": "odpri google", "response": "ok",
                                 "source": "voice", "intent": "open",
                                 "outcome": "success",
                                 "meta": {"entities": [{"kind": "app",
                                                        "value": "google"}]}})
        result = core.mine()
        self.assertGreaterEqual(len(result.get("candidates", [])), 1)
        self.assertGreaterEqual(core.status()["db"]["episodes"], 3)
        core.close()


if __name__ == "__main__":
    unittest.main()
