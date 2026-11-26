"""Tests for the capability checklist (catalog, detection, confirmation)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core import capabilities  # noqa: E402
from mia_core.db import Store  # noqa: E402


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "learning.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_catalog_is_rich_and_unique(self):
        self.assertGreaterEqual(len(capabilities.CATALOG), 70)
        ids = [item["id"] for item in capabilities.CATALOG]
        self.assertEqual(len(ids), len(set(ids)))
        for item in capabilities.CATALOG:
            self.assertTrue(item["category"])
            self.assertTrue(item["label"])
            self.assertTrue(item["how"])

    def test_refresh_detects_and_summarises(self):
        result = capabilities.refresh(self.store)
        self.assertGreaterEqual(result["checked"], 70)
        rows = self.store.list_capabilities(limit=500)
        self.assertGreaterEqual(len(rows), 70)
        self.assertTrue(any(r["status"] == "detected" for r in rows))
        summary = capabilities.summary(self.store)
        self.assertEqual(summary["total"], len(rows))
        self.assertIn("by_category", summary)
        self.assertGreaterEqual(summary["by_status"]["detected"], 1)

    def test_confirm_and_mark_learned(self):
        capabilities.refresh(self.store)
        self.assertTrue(capabilities.confirm(self.store, "files.search",
                                             "confirmed", "testirano"))
        row = self.store.get_capability("files.search")
        self.assertEqual(row["status"], "confirmed")
        self.assertEqual(row["notes"], "testirano")

        capabilities.mark_learned(self.store, "volume set", ok=True)
        vol = self.store.get_capability("audio.volume.set")
        self.assertEqual(vol["status"], "learned")

        lines = capabilities.lines(self.store, "datoteke")
        self.assertTrue(any("datoteke" in line.lower() or "Iskanje" in line
                            for line in lines))

    def test_confirmed_survives_refresh(self):
        capabilities.refresh(self.store)
        capabilities.confirm(self.store, "desktop.screenshot", "confirmed")
        capabilities.refresh(self.store)
        self.assertEqual(self.store.get_capability("desktop.screenshot")["status"],
                         "confirmed")

    def test_export_import_keeps_capabilities(self):
        capabilities.refresh(self.store)
        capabilities.confirm(self.store, "system.cpu", "confirmed", "videl")
        data = self.store.export_data()
        self.assertTrue(data.get("capabilities"))
        other = Store(Path(self.tmp.name) / "other.db")
        try:
            other.import_data(data)
            self.assertEqual(other.get_capability("system.cpu")["status"],
                             "confirmed")
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
