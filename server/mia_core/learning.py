"""LearningCore — one facade for episodes, habits, recipes, mistakes and skills.

Every public method is failure-isolated: a broken learning store must never take
the voice loop down. Errors are printed and reflected in `last_error`.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import threading
import time
from pathlib import Path
from typing import Any

from .config import load_config, repo_root, skills_root as cfg_skills_root
from .context import brief_preview, build_brief
from .db import Store
from .habits import mine_habits
from .integration import episode_payload
from .knowledge import scan_skill_tree, tree_payload, validate_tree
from .recipes import (learn_from_episode, match_anti_patterns, match_recipes,
                      record_feedback, remember_as_recipe)


class LearningCore:
    def __init__(self, cfg: dict | None = None, path: str | Path | None = None):
        if cfg and isinstance(cfg.get("learning"), dict):
            self.cfg = load_config(overrides=cfg["learning"])
        elif cfg:
            self.cfg = load_config(overrides=cfg)
        else:
            self.cfg = load_config()
        self.enabled = bool(self.cfg.get("enabled", True))
        self._path = Path(path).expanduser() if path else None
        self._store: Store | None = None
        self._lock = threading.RLock()
        self.last_error = ""
        self._skills_root = cfg_skills_root(self.cfg)

    # ------------------------------------------------------------- plumbing
    @property
    def store(self) -> Store:
        with self._lock:
            if self._store is None:
                path = self._path
                if path is None:
                    from .config import db_path
                    path = db_path(self.cfg)
                self._store = Store(path, privacy_cfg=self.cfg.get("privacy") or {})
            return self._store

    def _safe(self, default: Any, fn, *args, **kwargs) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # learning must never break a turn
            self.last_error = f"{type(exc).__name__}: {exc}"
            print(f"[mia-learning] {self.last_error}", flush=True)
            return default

    @property
    def skills_root(self) -> Path:
        return self._skills_root

    def close(self) -> None:
        with self._lock:
            if self._store is not None:
                self._store.close()
                self._store = None

    # ------------------------------------------------------------- episodes
    def record_episode(self, payload: dict, learn: bool = True) -> int | None:
        if not self.enabled:
            return None

        def run() -> int | None:
            ep_id = self.store.record_episode(**payload)
            if learn:
                episode = self.store.get_episode(ep_id)
                if episode:
                    learn_from_episode(self.store, episode, self.cfg)
            return ep_id

        return self._safe(None, run)

    def record_turn(self, timing: Any, conversation: str, transcript: str,
                    source: str = "voice", response: str | None = None,
                    tools: list[str] | None = None,
                    extra_meta: dict | None = None) -> int | None:
        if not self.enabled or not self.cfg.get("auto_record", True):
            return None
        payload = episode_payload(timing, conversation, transcript, source,
                                  response=response, tools=tools,
                                  extra_meta=extra_meta)
        if not payload.get("request"):
            return None
        return self.record_episode(payload)

    def record_chat(self, conversation: str, request: str, response: str,
                    tools: list[dict] | None = None, error: str = "",
                    duration_s: float | None = None) -> int | None:
        if not self.enabled or not self.cfg.get("auto_record", True):
            return None
        names = [t.get("name", "tool") for t in (tools or []) if isinstance(t, dict)]
        payload = episode_payload({}, conversation, request, "chat",
                                  response=response, tools=names)
        payload["error"] = error
        payload["outcome"] = ("failure" if error and not response else
                              "success" if response else "unknown")
        payload["duration_s"] = duration_s
        payload["steps"] = [{"tool": t.get("name"), "preview": t.get("preview", "")}
                            for t in (tools or []) if isinstance(t, dict)]
        return self.record_episode(payload)

    def record_control(self, action: str, args: list[str] | None = None,
                       ok: bool = True, error: str = "", duration_s: float = 0,
                       meta: dict | None = None) -> int | None:
        if not self.enabled:
            return None
        payload = {
            "session": "control",
            "source": "control",
            "intent": action,
            "request": f"{action} {' '.join(args or [])}".strip(),
            "response": "" if ok else error,
            "tools": ["mia-ctl"],
            "steps": [{"action": action, "args": args or [], "ok": ok}],
            "outcome": "success" if ok else "failure",
            "error": error,
            "duration_s": duration_s,
            "tags": ["control", action],
            "meta": meta or {},
        }
        return self.record_episode(payload)

    def finish_episode(self, episode_id: int, outcome: str | None = None,
                       response: str | None = None, error: str | None = None,
                       learn: bool = True) -> dict:
        if not self.enabled:
            return {"ok": False, "error": "learning disabled"}

        def run() -> dict:
            fields: dict[str, Any] = {}
            if outcome:
                fields["outcome"] = outcome
            if response is not None:
                fields["response"] = response
            if error is not None:
                fields["error"] = error
            self.store.update_episode(episode_id, **fields)
            episode = self.store.get_episode(episode_id)
            learned = learn_from_episode(self.store, episode, self.cfg) if (learn and episode) else {}
            return {"ok": True, "episode_id": episode_id, "learned": learned}

        return self._safe({"ok": False, "error": self.last_error}, run)

    def episodes(self, limit: int = 50, **kwargs: Any) -> list[dict]:
        return self._safe([], lambda: self.store.list_episodes(limit=limit, **kwargs))

    def events(self, limit: int = 100) -> list[dict]:
        return self._safe([], lambda: self.store.list_events(limit=limit))

    def feedback(self, episode_id: int, verdict: str, note: str = "") -> dict:
        return self._safe({"ok": False, "error": self.last_error},
                          lambda: record_feedback(self.store, episode_id, verdict,
                                                  note, self.cfg))

    def feedback_last(self, conversation: str, verdict: str, note: str = "") -> dict:
        def run() -> dict:
            episode = self.store.last_episode(session=conversation)
            if not episode:
                return {"ok": False, "error": "no previous episode"}
            result = record_feedback(self.store, int(episode["id"]), verdict, note, self.cfg)
            result["episode_id"] = episode["id"]
            return result

        return self._safe({"ok": False, "error": self.last_error}, run)

    def remember(self, episode_id: int, note: str = "") -> dict:
        return self._safe({"ok": False, "error": self.last_error},
                          lambda: remember_as_recipe(self.store, episode_id, note))

    def remember_last(self, conversation: str, note: str = "") -> dict:
        def run() -> dict:
            episode = self.store.last_episode(session=conversation)
            if not episode:
                return {"ok": False, "error": "no previous episode"}
            result = remember_as_recipe(self.store, int(episode["id"]), note)
            result["episode_id"] = episode["id"]
            return result

        return self._safe({"ok": False, "error": self.last_error}, run)

    # -------------------------------------------------------------- knowledge
    def tree(self) -> dict:
        return self._safe({"root": str(self._skills_root), "tree": [], "flat": [],
                           "summary": {}, "issues": []},
                          lambda: tree_payload(self._skills_root))

    def validate_tree(self) -> dict:
        return self._safe({"ok": False, "errors": [{"message": self.last_error}]},
                          lambda: validate_tree(self._skills_root))

    def refresh_skills(self) -> dict:
        def run() -> dict:
            nodes = scan_skill_tree(self._skills_root)
            self.store.replace_skill_nodes(nodes)
            payload = tree_payload(self._skills_root)
            self.store.add_event("skill_scan", str(self._skills_root),
                                 {"skills": len(nodes), **payload["summary"]})
            return {"ok": True, "skills": len(nodes), "summary": payload["summary"]}

        return self._safe({"ok": False, "error": self.last_error}, run)

    def search(self, query: str, limit: int = 30) -> list[dict]:
        return self._safe([], lambda: self.store.search(query, limit=limit))

    def brief(self, request: str = "") -> str:
        if not self.enabled:
            return ""
        return self._safe("", lambda: build_brief(self.store, self.cfg, request,
                                                  self._skills_root))

    def brief_preview(self, request: str = "") -> dict:
        return self._safe({"chars": 0, "text": ""},
                          lambda: brief_preview(self.store, self.cfg, request,
                                                self._skills_root))

    # ---------------------------------------------------------------- memory
    def habits(self, limit: int = 50, min_confidence: float = 0.0) -> list[dict]:
        return self._safe([], lambda: self.store.list_habits(limit, min_confidence))

    def recipes(self, limit: int = 50, min_confidence: float = 0.0) -> list[dict]:
        return self._safe([], lambda: self.store.list_recipes(limit, min_confidence))

    def mistakes(self, limit: int = 50) -> list[dict]:
        return self._safe([], lambda: self.store.list_anti_patterns(limit))

    def facts(self, limit: int = 100, kind: str | None = None) -> list[dict]:
        return self._safe([], lambda: self.store.list_facts(limit, kind))

    def match(self, request: str) -> dict:
        def run() -> dict:
            return {
                "recipes": match_recipes(
                    self.store, request, limit=3,
                    threshold=float((self.cfg.get("recipes") or {})
                                    .get("match_threshold", 0.52))),
                "mistakes": match_anti_patterns(self.store, request, limit=3),
            }

        return self._safe({"recipes": [], "mistakes": []}, run)

    def set_fact(self, key: str, value: str, kind: str = "preference",
                 tags: list[str] | None = None, confidence: float = 0.8,
                 source: str = "user") -> int:
        return self._safe(0, lambda: self.store.upsert_fact(
            key, value, kind=kind, tags=tags or [], confidence=confidence,
            source=source))

    def add_recipe(self, title: str, steps: list[Any], key: str | None = None,
                   tags: list[str] | None = None, notes: str = "") -> int:
        from .recipes import recipe_key
        return self._safe(0, lambda: self.store.upsert_recipe(
            key or recipe_key(title), title=title, steps=steps,
            tags=tags or [], notes=notes, source="user", success=1))

    def add_mistake(self, symptom: str, cause: str = "", fix: str = "",
                    tags: list[str] | None = None, severity: str = "medium") -> int:
        import hashlib
        from .recipes import recipe_key
        digest = hashlib.sha1((cause or "").encode("utf-8", "ignore")).hexdigest()[:10]
        return self._safe(0, lambda: self.store.upsert_anti_pattern(
            key=f"ap:{recipe_key(symptom)}:{digest}",
            symptom=symptom, cause=cause, fix=fix, tags=tags or [],
            severity=severity))

    def pin_habit(self, key: str, pinned: bool = True) -> bool:
        return self._safe(False, lambda: self.store._execute(
            "UPDATE habits SET pinned=? WHERE key=?",
            (1 if pinned else 0, key)).rowcount > 0)

    def delete(self, kind: str, key_or_id: str | int) -> bool:
        table = {"recipe": "recipes", "mistake": "anti_patterns",
                 "habit": "habits", "fact": "facts"}.get(kind)
        if not table:
            return False
        column = "key" if isinstance(key_or_id, str) and not str(key_or_id).isdigit() else "id"
        return self._safe(False, lambda: self.store._execute(
            f"DELETE FROM {table} WHERE {column}=?", (key_or_id,)).rowcount > 0)

    # ------------------------------------------------------------------ jobs
    def mine(self, ingest_audit: bool = True) -> dict:
        def run() -> dict:
            result = mine_habits(self.store, self.cfg, apply=True)
            if ingest_audit:
                audit = self.cfg.get("audit_path") or ""
                if audit:
                    from .config import expand_path
                    path = expand_path(audit)
                    result["audit_records"] = self.store.ingest_audit(path)
            result["skills"] = self.refresh_skills()
            self.store.meta_set("last_mine_ts", time.time())
            return result

        return self._safe({"error": self.last_error}, run)

    def prune(self) -> dict:
        def run() -> dict:
            rcfg = self.cfg.get("retention") or {}
            return self.store.prune(
                episodes_days=int(rcfg.get("episodes_days", 400)),
                events_days=int(rcfg.get("events_days", 180)),
                max_episodes=int(rcfg.get("max_episodes", 200000)),
                min_confidence=float(rcfg.get("min_confidence", 0.12)),
            )

        return self._safe({"error": self.last_error}, run)

    def system_facts(self) -> dict:
        def run() -> dict:
            root = repo_root()
            tools = {name: bool(shutil.which(name)) for name in (
                "xdotool", "wmctrl", "grim", "gnome-screenshot", "spectacle",
                "scrot", "import", "wl-copy", "wl-paste", "xclip", "xsel",
                "notify-send", "playerctl", "pactl", "wpctl", "brightnessctl",
                "systemctl", "loginctl", "ydotool", "wtype", "swaymsg",
                "hyprctl", "osascript", "screencapture", "cliclick", "nmcli",
                "nvidia-smi", "yt-dlp")}
            info = {
                "os": f"{platform.system()} {platform.release()}",
                "machine": platform.machine(),
                "hostname": socket.gethostname(),
                "python": platform.python_version(),
                "user": os_user(),
                "repo": str(root),
                "desktop_session": os_environ("XDG_SESSION_TYPE") or
                                   ("wayland" if os_environ("WAYLAND_DISPLAY") else
                                    "x11" if os_environ("DISPLAY") else "headless"),
                "desktop": os_environ("XDG_CURRENT_DESKTOP") or "",
                "display": os_environ("DISPLAY") or "",
                "tools": ", ".join(sorted(k for k, v in tools.items() if v)) or "none",
                "missing_tools": ", ".join(sorted(k for k, v in tools.items() if not v)),
                "cpu_count": str(os.cpu_count() or ""),
            }
            for key, value in info.items():
                if value:
                    kind = ("inventory" if key in ("tools", "missing_tools", "cpu_count")
                            else "system")
                    self.store.upsert_fact(f"system.{key}", str(value), kind=kind,
                                           source="system-scan", confidence=0.95)
            self.store.add_event("system_scan", socket.gethostname(), info)
            return info

        return self._safe({"error": self.last_error}, run)

    def status(self) -> dict:
        def run() -> dict:
            stats = self.store.stats()
            tree = tree_payload(self._skills_root)
            return {
                "enabled": self.enabled,
                "db": stats,
                "skills": tree.get("summary", {}),
                "last_mine_ts": float(self.store.meta_get("last_mine_ts", "0") or 0),
                "audit_path": str(self.cfg.get("audit_path") or ""),
                "context_max_chars": int((self.cfg.get("context") or {})
                                         .get("max_chars", 1500)),
                "last_error": self.last_error,
            }

        return self._safe({"enabled": self.enabled, "error": self.last_error}, run)

    def export(self, dest: str | Path) -> Path:
        def run() -> Path:
            import json
            dest_path = Path(dest).expanduser()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(json.dumps(self.store.export_data(),
                                            ensure_ascii=False, indent=1),
                                 encoding="utf-8")
            return dest_path

        return self._safe(Path(dest), run)

    def import_(self, src: str | Path, merge: bool = True) -> dict:
        def run() -> dict:
            import json
            data = json.loads(Path(src).expanduser().read_text(encoding="utf-8"))
            return self.store.import_data(data, merge=merge)

        return self._safe({"error": self.last_error}, run)

    def backup(self, dest: str | Path) -> Path:
        return self._safe(Path(dest), lambda: self.store.backup(dest))


def os_environ(name: str) -> str:
    import os
    return os.environ.get(name, "")


def os_user() -> str:
    import getpass
    try:
        return getpass.getuser()
    except Exception:
        return ""


_CORE: LearningCore | None = None
_CORE_LOCK = threading.Lock()


def get_core(cfg: dict | None = None, reset: bool = False) -> LearningCore:
    global _CORE
    with _CORE_LOCK:
        if _CORE is None or reset:
            if _CORE is not None:
                _CORE.close()
            _CORE = LearningCore(cfg)
        return _CORE
