"""Mia Core — durable learning, knowledge tree and local control support.

The package is deliberately stdlib-only so it can run inside the voice server,
inside small CLI helpers and in tests on machines without the full Mia stack.
"""

from .learning import LearningCore, get_core
from .config import DEFAULT_CONFIG, load_config
from .knowledge import scan_skill_tree, tree_payload, validate_tree
from .recipes import normalize, recipe_key
from .habits import mine_habits

__all__ = [
    "LearningCore", "get_core", "DEFAULT_CONFIG", "load_config",
    "scan_skill_tree", "tree_payload", "validate_tree",
    "normalize", "recipe_key", "mine_habits",
]

__version__ = "1.0.0"
