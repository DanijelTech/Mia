"""Tests for the mia_learning Hermes plugin (no network)."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "hermes-plugin" / "mia_learning"


def load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"mia_learning_{name}", PLUGIN / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = load("tools")
        cls.schemas = load("schemas")

    def test_provides_tools_exist(self):
        import re
        yaml_text = (PLUGIN / "plugin.yaml").read_text()
        names = re.findall(r"^\s+-\s+(\w+)$", yaml_text, re.M)
        self.assertGreaterEqual(len(names), 8)
        for name in names:
            self.assertTrue(hasattr(self.tools, name), f"missing handler {name}")

    def test_schemas_match_handlers(self):
        for attr in dir(self.schemas):
            if not attr.isupper():
                continue
            schema = getattr(self.schemas, attr)
            if not isinstance(schema, dict) or "name" not in schema:
                continue
            self.assertTrue(hasattr(self.tools, schema["name"]),
                            f"schema {schema['name']} has no handler")

    def test_handlers_use_the_api(self):
        calls = []

        def fake(method, path, payload=None):
            calls.append((method, path, payload))
            if path.startswith("/status"):
                return {"enabled": True, "db": {"episodes": 1}}
            if path.startswith("/brief"):
                return {"chars": 10, "text": "[MIA SPOMIN]"}
            if path.startswith("/tree"):
                return {"flat": [{"name": "mia-desktop", "description": "windows"}]}
            return {"ok": True}

        self.tools._request = fake  # type: ignore[assignment]

        self.assertIn("MIA SPOMIN", self.tools.memory_brief({"request": "open google"}))
        self.assertTrue(json.loads(self.tools.memory_search({"query": "google"}))["ok"])
        self.assertTrue(json.loads(self.tools.memory_feedback(
            {"verdict": "negative", "note": "prefer Chrome"}))["ok"])
        self.assertTrue(json.loads(self.tools.memory_remember({"note": "works"}))["ok"])
        self.assertTrue(json.loads(self.tools.memory_fact(
            {"key": "pref.browser", "value": "firefox"}))["ok"])
        self.assertTrue(json.loads(self.tools.memory_mistake(
            {"symptom": "pkill leaks", "fix": "mia-close"}))["ok"])
        self.assertTrue(json.loads(self.tools.memory_status({}))["enabled"])
        tree = json.loads(self.tools.skill_tree({"query": "windows"}))
        self.assertEqual(tree["matches"][0]["name"], "mia-desktop")
        self.assertTrue(calls)

    def test_missing_required_fields(self):
        self.assertIn("error", json.loads(self.tools.memory_brief({})))
        self.assertIn("error", json.loads(self.tools.memory_search({})))
        self.assertIn("error", json.loads(self.tools.memory_fact({"key": ""})))
        self.assertIn("error", json.loads(self.tools.memory_mistake({})))


if __name__ == "__main__":
    unittest.main()
