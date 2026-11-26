"""Tests for the audited desktop-control CLI (headless-safe)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CTL = ROOT / "skills" / "mia-companion" / "bin" / "mia-ctl"


class CtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "Documents").mkdir()
        (self.home / "Documents" / "invoice-2026.txt").write_text("hello")
        (self.home / ".ssh").mkdir()
        (self.home / ".ssh" / "id_rsa").write_text("secret")
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_RUNTIME_DIR": str(self.home / ".run"),
        })
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "SWAYSOCK",
                    "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"):
            self.env.pop(key, None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_ctl(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CTL), *args],
                              capture_output=True, text=True, env=self.env, timeout=60)

    def test_doctor_json(self):
        result = self.run_ctl("doctor", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["desktop"], "headless")
        self.assertIn("tools", payload["data"])

    def test_sysinfo(self):
        result = self.run_ctl("sysinfo", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)["data"]
        self.assertTrue(data["os"])
        self.assertGreater(data["cpu"]["cores"], 0)

    def test_files_search(self):
        result = self.run_ctl("files", "search", "invoice", "--root",
                              str(self.home / "Documents"), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)["data"]
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]["path"].endswith("invoice-2026.txt"))

    def test_policy_allows_home_and_denies_ssh(self):
        allowed = self.run_ctl("policy", "check", str(self.home / "Documents"),
                               "--json")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertTrue(json.loads(allowed.stdout)["ok"])

        denied = self.run_ctl("policy", "check", str(self.home / ".ssh" / "id_rsa"),
                              "--json")
        self.assertEqual(denied.returncode, 4)
        payload = json.loads(denied.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("deny", payload["error"])

    def test_files_search_outside_roots_is_denied(self):
        result = self.run_ctl("files", "search", "id_rsa", "--root",
                              str(self.home / ".ssh"))
        self.assertEqual(result.returncode, 4)
        self.assertIn("deny", result.stderr.lower())

    def test_dry_run_does_not_need_a_backend(self):
        result = self.run_ctl("--dry-run", "type", "hello", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["data"]["would"], "type")

    def test_windows_unsupported_in_headless(self):
        result = self.run_ctl("windows", "list")
        self.assertEqual(result.returncode, 3)
        self.assertIn("window manager", result.stderr.lower())

    def test_protected_pid_cannot_be_killed(self):
        result = self.run_ctl("process", "kill", "1", "--yes", "--json")
        self.assertEqual(result.returncode, 4)
        self.assertIn("protected", json.loads(result.stdout)["error"].lower())

    def test_power_needs_confirmation(self):
        result = self.run_ctl("power", "reboot", "--json")
        self.assertEqual(result.returncode, 4)
        self.assertIn("requires --yes", json.loads(result.stdout)["error"])

    def test_service_allowlist(self):
        result = self.run_ctl("service", "restart", "nginx", "--yes", "--json")
        self.assertEqual(result.returncode, 4)
        self.assertIn("allow_service_control", json.loads(result.stdout)["error"])

    def test_custom_policy_can_disable_power(self):
        cfg = self.home / ".config" / "mia"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "control.json").write_text(json.dumps({"allow_power": False}))
        result = self.run_ctl("power", "lock", "--json")
        self.assertEqual(result.returncode, 4)
        self.assertIn("disabled by policy", json.loads(result.stdout)["error"])

    def test_audit_is_written_and_redacted(self):
        self.run_ctl("files", "search", "invoice", "--root",
                     str(self.home / "Documents"))
        audit = self.home / ".local" / "state" / "mia" / "control-audit.jsonl"
        self.assertTrue(audit.exists())
        lines = audit.read_text().splitlines()
        self.assertTrue(lines)
        record = json.loads(lines[-1])
        self.assertEqual(record["action"], "files search")
        self.assertTrue(record["ok"])
        self.assertIn("ts", record)
        self.assertIn("host", record)

        self.run_ctl("clipboard", "set", "sk-abcdefghijklmnopqrstuvwxyz123456")
        last = json.loads(audit.read_text().splitlines()[-1])
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456",
                         json.dumps(last))

    def test_audit_tail(self):
        self.run_ctl("sysinfo")
        result = self.run_ctl("audit", "tail", "--limit", "5", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)["data"]
        self.assertTrue(data)
        self.assertIn("action", data[-1])


if __name__ == "__main__":
    unittest.main()
