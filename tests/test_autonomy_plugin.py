"""Tests for the mia_autonomy Hermes plugin (no network)."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "hermes-plugin" / "mia_autonomy"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"mia_autonomy_{name}",
                                                  PLUGIN / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class AutonomyPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = load("tools")
        cls.schemas = load("schemas")

    def test_provides_tools_exist(self):
        names = re.findall(r"^\s+-\s+(\w+)$",
                           (PLUGIN / "plugin.yaml").read_text(), re.M)
        self.assertGreaterEqual(len(names), 12)
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
                return {"score": {"percent": 60}, "scheduler": {"total": 1}}
            if path.startswith("/health"):
                return {"level": "ok", "score": 100}
            if path.startswith("/profile"):
                return {"summary": "Debian"}
            if path.startswith("/plans"):
                return {"plans": [{"name": "cleanup"}]}
            if path.startswith("/run"):
                return {"ok": True, "task_id": 3}
            if path.startswith("/text"):
                return {"handled": True, "text": "Glasnost 40."}
            if path.startswith("/jobs") and method == "POST":
                return {"ok": True, "job": {"id": 1}}
            if path.startswith("/jobs") and method == "DELETE":
                return {"ok": True}
            if path.startswith("/jobs"):
                return {"jobs": []}
            if path.startswith("/tasks/1/resume"):
                return {"ok": True}
            if path.startswith("/tasks/1/cancel"):
                return {"ok": True}
            if path.startswith("/tasks"):
                return {"tasks": []}
            if path.startswith("/alerts/1/ack"):
                return {"ok": True}
            if path.startswith("/alerts"):
                return {"alerts": []}
            if path.startswith("/adapt"):
                return {"ok": True, "items": []}
            return {"ok": True}

        self.tools._request = fake  # type: ignore[assignment]

        self.assertEqual(json.loads(self.tools.system_status({}))["score"]["percent"], 60)
        self.assertEqual(json.loads(self.tools.system_health({}))["level"], "ok")
        self.assertEqual(json.loads(self.tools.system_profile({}))["summary"], "Debian")
        self.assertTrue(json.loads(self.tools.system_plans({}))["plans"])
        self.assertTrue(json.loads(self.tools.system_run_plan(
            {"template": "cleanup", "confirm": True}))["ok"])
        self.assertTrue(json.loads(self.tools.system_command(
            {"input": "set volume to 40"}))["handled"])
        self.assertTrue(json.loads(self.tools.system_job_add(
            {"name": "x", "trigger": {"kind": "every", "seconds": 60},
             "notify": "Mia", "text": "hi"}))["ok"])
        self.assertTrue(json.loads(self.tools.system_job_remove({"job_id": 1}))["ok"])
        self.assertTrue(json.loads(self.tools.system_task_resume({"task_id": 1}))["ok"])
        self.assertTrue(json.loads(self.tools.system_task_cancel({"task_id": 1}))["ok"])
        self.assertTrue(json.loads(self.tools.system_alert_ack({"alert_id": 1}))["ok"])
        self.assertTrue(calls)

    def test_missing_required_fields(self):
        for call, payload in (
            (self.tools.system_run_plan, {}),
            (self.tools.system_command, {}),
            (self.tools.system_job_add, {}),
            (self.tools.system_job_remove, {}),
            (self.tools.system_task_resume, {}),
            (self.tools.system_task_cancel, {}),
            (self.tools.system_alert_ack, {}),
        ):
            with self.subTest(call=call.__name__):
                self.assertIn("error", json.loads(call(payload)))


if __name__ == "__main__":
    unittest.main()
