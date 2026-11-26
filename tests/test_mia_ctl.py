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
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
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

    # ------------------------------------------------------------ new verbs
    def test_files_lifecycle(self):
        source = self.home / "Documents" / "invoice-2026.txt"
        target = self.home / "Documents" / "copy.txt"
        archive = self.home / "doc.zip"
        out = self.home / "out"

        info = self.run_ctl("files", "info", str(source), "--json")
        self.assertEqual(info.returncode, 0, info.stderr)
        self.assertEqual(json.loads(info.stdout)["data"]["type"], "file")

        mkdir = self.run_ctl("files", "mkdir", str(self.home / "newdir"), "--json")
        self.assertEqual(mkdir.returncode, 0, mkdir.stderr)
        self.assertTrue((self.home / "newdir").is_dir())

        copy = self.run_ctl("files", "copy", str(source), str(target), "--json")
        self.assertEqual(copy.returncode, 0, copy.stderr)
        self.assertTrue(target.exists())

        packed = self.run_ctl("files", "archive", str(self.home / "Documents"),
                              str(archive), "--json")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.assertTrue(archive.exists())

        unpacked = self.run_ctl("files", "extract", str(archive), str(out), "--json")
        self.assertEqual(unpacked.returncode, 0, unpacked.stderr)
        self.assertTrue(any(out.rglob("invoice-2026.txt")))

        trashed = self.run_ctl("files", "trash", str(target), "--yes", "--json")
        self.assertEqual(trashed.returncode, 0, trashed.stderr)
        self.assertFalse(target.exists())
        self.assertTrue((self.home / ".local" / "share" / "Trash" / "info").is_dir())

    def test_files_delete_requires_confirmation(self):
        target = self.home / "Documents" / "invoice-2026.txt"
        denied = self.run_ctl("files", "delete", str(target), "--json")
        self.assertEqual(denied.returncode, 4)
        self.assertTrue(target.exists())
        deleted = self.run_ctl("files", "delete", str(target), "--yes", "--json")
        self.assertEqual(deleted.returncode, 0, deleted.stderr)
        self.assertFalse(target.exists())

    def test_files_move_requires_confirmation(self):
        source = self.home / "Documents" / "invoice-2026.txt"
        target = self.home / "Documents" / "moved.txt"
        denied = self.run_ctl("files", "move", str(source), str(target), "--json")
        self.assertEqual(denied.returncode, 4)
        moved = self.run_ctl("files", "move", str(source), str(target),
                             "--yes", "--json")
        self.assertEqual(moved.returncode, 0, moved.stderr)
        self.assertTrue(target.exists())

    def test_extract_blocks_path_traversal(self):
        import zipfile
        evil = self.home / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("../escaped.txt", "bad")
        result = self.run_ctl("files", "extract", str(evil),
                              str(self.home / "safe"), "--json")
        self.assertEqual(result.returncode, 4)
        self.assertFalse((self.home / "escaped.txt").exists())

    def test_package_manager_and_install_dry_run(self):
        manager = self.run_ctl("pkg", "manager", "--json")
        self.assertEqual(manager.returncode, 0, manager.stderr)
        data = json.loads(manager.stdout)["data"]
        self.assertIn("manager", data)
        planned = self.run_ctl("--dry-run", "pkg", "install", "htop", "--yes",
                               "--json")
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertTrue(json.loads(planned.stdout)["data"]["dry_run"])
        blocked = self.run_ctl("pkg", "install", "htop", "--json")
        self.assertEqual(blocked.returncode, 4)
        self.assertIn("requires --yes", json.loads(blocked.stdout)["error"])

    def test_system_and_network_reads(self):
        for command in (("sys", "time"), ("sys", "timezone"), ("sys", "users"),
                        ("sys", "locale"), ("net", "dns"), ("net", "ports"),
                        ("net", "firewall", "status")):
            with self.subTest(command=command):
                result = self.run_ctl(*command, "--json")
                self.assertIn(result.returncode, (0, 3), result.stderr)

    def test_wifi_password_is_redacted_from_audit(self):
        result = self.run_ctl("net", "wifi", "connect", "TestNet", "tajno123",
                              "--json")
        self.assertIn(result.returncode, (0, 3), result.stderr)
        audit = self.home / ".local" / "state" / "mia" / "control-audit.jsonl"
        self.assertTrue(audit.exists())
        last = json.loads(audit.read_text().splitlines()[-1])
        joined = json.dumps(last)
        self.assertNotIn("tajno123", joined)
        self.assertIn("[REDACTED]", joined)

    def test_dry_run_does_not_touch_files(self):
        target = self.home / "ghost"
        result = self.run_ctl("--dry-run", "files", "mkdir", str(target), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["data"]["dry_run"])
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
