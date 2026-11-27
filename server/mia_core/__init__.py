"""Mia Core — durable learning, knowledge tree and local control support.

The package is deliberately stdlib-only so it can run inside the voice server,
inside small CLI helpers and in tests on machines without the full Mia stack.
"""

from __future__ import annotations

from pathlib import Path


def _read_version() -> str:
    for parent in Path(__file__).resolve().parents:
        version_file = parent / "VERSION"
        if version_file.is_file():
            try:
                value = version_file.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except OSError:
                pass
    return "1.1.0"


__version__ = _read_version()

from .learning import LearningCore, get_core  # noqa: E402
from .config import DEFAULT_CONFIG, load_config  # noqa: E402
from .knowledge import scan_skill_tree, tree_payload, validate_tree  # noqa: E402
from .recipes import normalize, recipe_key  # noqa: E402
from .habits import mine_habits  # noqa: E402

__all__ = [
    "LearningCore", "get_core", "DEFAULT_CONFIG", "load_config",
    "scan_skill_tree", "tree_payload", "validate_tree",
    "normalize", "recipe_key", "mine_habits", "__version__",
]
