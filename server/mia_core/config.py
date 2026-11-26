"""Configuration loading with safe defaults.

Values come from (highest priority last):
  1. DEFAULT_CONFIG
  2. MIA_LEARNING_* environment variables
  3. the `learning:` block of server/config/server.yaml
  4. explicit overrides (tests)
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "db_path": "~/.local/state/mia/learning.db",
    "audit_path": "~/.local/state/mia/control-audit.jsonl",
    "skills_root": None,                 # None = <repo>/skills
    "auto_record": True,                 # record every voice/typed turn
    "auto_feedback": True,               # accept "to je bilo prav / ni prav"
    "auto_mine_interval_seconds": 900,   # habit mining + audit ingest
    "context": {
        "enabled": True,
        "max_chars": 1500,
        "max_habits": 6,
        "max_recipes": 2,
        "max_mistakes": 3,
        "max_facts": 5,
        "include_skills": True,
        "include_system": True,
    },
    "retention": {
        "episodes_days": 400,
        "events_days": 180,
        "max_episodes": 200000,
        "min_confidence": 0.12,
    },
    "habits": {
        "min_evidence": 3,
        "recency_days": 120,
        "peak_share": 0.35,
        "sequence_window_minutes": 20,
        "decay_after_days": 45,
    },
    "recipes": {
        "match_threshold": 0.52,
        "max_candidates": 3,
        "min_success": 1,
        "saturation": 3.0,
    },
    "privacy": {
        "redact": True,
        "max_text_chars": 4000,
        "max_response_chars": 2000,
    },
    "autonomy": {
        "enabled": True,
        "interval_seconds": 30,
        "health_interval": 300,
        "profile_ttl": 300,
        "max_jobs_per_tick": 3,
        "temp_max_age_hours": 48,
        "allow_destructive": False,
        "auto_install": False,
        "auto_remediate": False,
    },
}

_ENV_MAP = {
    "MIA_LEARNING_ENABLED": ("enabled", bool),
    "MIA_LEARNING_DB": ("db_path", str),
    "MIA_LEARNING_AUDIT": ("audit_path", str),
    "MIA_SKILLS_ROOT": ("skills_root", str),
    "MIA_LEARNING_CONTEXT_MAX_CHARS": ("context.max_chars", int),
    "MIA_LEARNING_MINE_INTERVAL": ("auto_mine_interval_seconds", int),
}


def _coerce(value: str, kind: type) -> Any:
    if kind is bool:
        return value.strip().lower() in ("1", "true", "yes", "on")
    if kind is int:
        return int(float(value))
    return value


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        elif value is not None:
            out[key] = value
    return out


def _apply_env(cfg: dict) -> dict:
    for env_name, (path, kind) in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            value = _coerce(raw, kind)
        except (TypeError, ValueError):
            continue
        parts = path.split(".")
        node = cfg
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return cfg


def _load_yaml_learning(path: Path) -> dict:
    """Read only the `learning:` block; tolerate a missing PyYAML.

    The server has PyYAML, but small CLIs and tests may not. The fallback is a
    deliberately tiny indentation parser that covers the documented shape.
    """
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data.get("learning") or {}
    except Exception:
        return _parse_learning_block(path)


def _parse_learning_block(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: dict = {}
    stack: list[tuple[int, dict]] = [(-1, out)]
    in_block = False
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            in_block = line.startswith("learning:")
            stack = [(-1, out)]
            continue
        if not in_block or ":" not in line:
            continue
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return out


def _parse_scalar(value: str) -> Any:
    value = value.split(" #", 1)[0].strip()
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None", "~"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(v) for v in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip('"').strip("'")


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config" / "server.yaml"
    cfg = _deep_merge(cfg, _load_yaml_learning(Path(path)))
    cfg = _apply_env(cfg)
    cfg = _deep_merge(cfg, overrides or {})
    return cfg


def expand_path(value: str | Path, base: Path | None = None) -> Path:
    p = Path(os.path.expandvars(str(value))).expanduser()
    if not p.is_absolute() and base is not None:
        p = base / p
    return p


def repo_root() -> Path:
    """Best-effort Mia repository root (the parent of `server/`)."""
    env = os.environ.get("MIA_HOME")
    if env:
        candidate = Path(env).expanduser()
        if (candidate / "server").is_dir() or (candidate / "skills").is_dir():
            return candidate
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "skills").is_dir() and (parent / "server").is_dir():
            return parent
    pointer = Path.home() / ".config" / "mia" / "home"
    if pointer.exists():
        candidate = Path(pointer.read_text(encoding="utf-8").strip()).expanduser()
        if candidate.is_dir():
            return candidate
    return here.parent.parent.parent


def db_path(cfg: dict) -> Path:
    return expand_path(cfg.get("db_path") or DEFAULT_CONFIG["db_path"])


def skills_root(cfg: dict) -> Path:
    value = cfg.get("skills_root")
    return expand_path(value) if value else repo_root() / "skills"
