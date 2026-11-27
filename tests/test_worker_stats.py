"""The GPU worker stats agent must answer /stats without a NameError."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "worker" / "worker_stats.py"


def _load():
    spec = importlib.util.spec_from_file_location("mia_worker_stats", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class WorkerStatsTests(unittest.TestCase):
    def test_stats_has_name_and_online(self):
        module = _load()
        data = module.stats()
        self.assertTrue(data["name"])
        self.assertTrue(data["online"])

    def test_gpu_stats_is_a_dict_without_a_gpu(self):
        module = _load()
        self.assertIsInstance(module.gpu_stats(), dict)


if __name__ == "__main__":
    unittest.main()
