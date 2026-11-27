"""Tests for the chat-vs-agent router and the optional chat brain gating."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core.brain import classify_brain  # noqa: E402
from chat_brain import ChatBrain, EscalateToAgent  # noqa: E402


class ChatBrainLanguageTests(unittest.TestCase):
    def _brain(self):
        return ChatBrain({"llm": {"router": {"enabled": True},
                                  "chat": {"enabled": True,
                                           "base_url": "http://127.0.0.1:1/v1"}}})

    def test_forced_language_adds_a_system_instruction(self):
        brain = self._brain()
        brain.force_lang = "English"
        messages = brain._messages("hello", "c", "")
        self.assertEqual(messages[1]["role"], "system")
        self.assertIn("English", messages[1]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "hello"})

    def test_no_forced_language_keeps_the_config_prompt_only(self):
        brain = self._brain()
        self.assertEqual(len(brain._messages("hello", "c", "")), 2)


class BrainRouterTests(unittest.TestCase):
    def test_casual_chat_stays_on_chat(self):
        for text in (
            "Kako si?",
            "Kdo si ti?",
            "Povej mi vic.",
            "Kaj misliš o tem vremenu?",
            "Kaj je glavno mesto Slovenije?",
            "Hvala, to je bilo lepo.",
            "Kako se imaš?",
            "Povej mi nekaj zanimivega.",
        ):
            self.assertEqual(classify_brain(text), "chat", text)

    def test_actions_go_to_agent(self):
        for text in (
            "Odpri brskalnik.",
            "Zaženi Spotify.",
            "Zapri okno.",
            "Poišči recept za potico.",
            "Preberi datoteko /home/user/opombe.txt",
            "Pošlji to Ani.",
            "Nastavi opomnik za jutri.",
            "Preveri stanje CPU.",
            "Odpri https://example.com",
            "Prenesi to datoteko.",
            "Namesti paket.",
            "Posodobi sistem.",
        ):
            self.assertEqual(classify_brain(text), "agent", text)

    def test_live_data_goes_to_agent(self):
        for text in ("Kakšno je vreme danes?", "Povej mi novice.",
                     "Koliko je cena delnice?"):
            self.assertEqual(classify_brain(text), "agent", text)

    def test_empty_is_chat(self):
        self.assertEqual(classify_brain(""), "chat")
        self.assertEqual(classify_brain("   "), "chat")

    def test_leading_directive_is_ignored(self):
        self.assertEqual(
            classify_brain("[note: your previous reply was cut off] Kako si?"),
            "chat")


class ChatBrainGatingTests(unittest.TestCase):
    def test_disabled_router_always_agent(self):
        brain = ChatBrain({"llm": {
            "router": {"enabled": False},
            "chat": {"enabled": True, "base_url": "http://127.0.0.1:1/v1"},
        }})
        self.assertFalse(brain.enabled)
        self.assertEqual(brain.choose("Kako si?"), "agent")

    def test_missing_base_url_disables_chat(self):
        brain = ChatBrain({"llm": {
            "router": {"enabled": True},
            "chat": {"enabled": True},
        }})
        self.assertFalse(brain.enabled)
        self.assertEqual(brain.choose("Kako si?"), "agent")

    def test_enabled_router_splits(self):
        brain = ChatBrain({"llm": {
            "router": {"enabled": True},
            "chat": {"enabled": True, "base_url": "http://127.0.0.1:1/v1"},
        }})
        self.assertTrue(brain.enabled)
        self.assertEqual(brain.choose("Kako si?"), "chat")
        self.assertEqual(brain.choose("Odpri brskalnik."), "agent")

    def test_sentinel_is_an_exception_type(self):
        self.assertTrue(issubclass(EscalateToAgent, RuntimeError))


class ChatBrainContextTests(unittest.TestCase):
    def _brain(self):
        return ChatBrain({"llm": {
            "router": {"enabled": True},
            "chat": {"enabled": True, "base_url": "http://127.0.0.1:1/v1",
                     "history_turns": 2},
        }})

    def test_note_and_recent(self):
        brain = self._brain()
        brain.note("mia-main", "odpri brskalnik", "Odprla sem brskalnik.")
        recent = brain.recent("mia-main")
        self.assertIn("Uporabnik: odpri brskalnik", recent)
        self.assertIn("Mia: Odprla sem brskalnik.", recent)

    def test_note_ignores_empty(self):
        brain = self._brain()
        brain.note("mia-main", "", "x")
        self.assertEqual(brain.recent("mia-main"), "")

    def test_recent_keeps_the_last_turns(self):
        brain = self._brain()
        for i in range(10):
            brain.note("mia-main", f"u{i}", f"a{i}")
        recent = brain.recent("mia-main", 2)
        self.assertIn("u9", recent)
        self.assertNotIn("u0", recent)


if __name__ == "__main__":
    unittest.main()
