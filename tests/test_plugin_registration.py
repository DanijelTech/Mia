"""Both Mia plugins must actually register their tools with Hermes."""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = {"mia_learning": ROOT / "hermes-plugin" / "mia_learning",
           "mia_autonomy": ROOT / "hermes-plugin" / "mia_autonomy"}


class _Ctx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler):
        self.tools[name] = {"toolset": toolset, "schema": schema,
                            "handler": handler}


def _load_package(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(
        name, path / "__init__.py", submodule_search_locations=[str(path)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class PluginRegistrationTests(unittest.TestCase):
    def test_every_declared_tool_is_registered(self):
        for name, path in PLUGINS.items():
            with self.subTest(plugin=name):
                module = _load_package(name, path)
                ctx = _Ctx()
                module.register(ctx)
                declared = re.findall(r"^\s+-\s+(\w+)$",
                                      (path / "plugin.yaml").read_text(), re.M)
                self.assertGreaterEqual(len(declared), 8)
                self.assertEqual(set(declared), set(ctx.tools))
                for tool in ctx.tools.values():
                    self.assertTrue(callable(tool["handler"]))
                    self.assertEqual(tool["schema"]["name"],
                                     next(k for k, v in ctx.tools.items()
                                          if v is tool))


if __name__ == "__main__":
    unittest.main()
