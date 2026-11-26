"""AutonomyService — one facade the server and the CLI both use.

It owns the profile, planner, scheduler and health watchdog, and turns a
recognised natural-language intent into a real, audited machine action.

Design rules:
* every action goes through `mia-ctl` (policy + audit) or the planner,
* confirmations are persisted, so a "ja" works after a restart,
* a failure returns a spoken sentence, never an exception,
* autonomy is fail-open: a broken subsystem must not break the voice loop.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from ..config import db_path, load_config
from ..db import Store
from . import health as health_mod
from .intents import Intent, fold, route, route_help
from .planner import Planner, build_template, ctl_argv, find_ctl, make_plan
from .profile import get_profile
from .scheduler import Scheduler, plan_for_reminder, trigger_summary

DEFAULT_AUTONOMY = {
    "enabled": True,
    "interval_seconds": 30,
    "health_interval": 300,
    "profile_ttl": 300,
    "max_jobs_per_tick": 3,
    "temp_max_age_hours": 48,
    "allow_destructive": False,
    "auto_install": False,
    "auto_remediate": False,
}

_YES = ("ja", "da", "potrdi", "potrjujem", "izvrsi", "naredi", "kar naredi",
        "seveda", "ok", "okej", "go", "yes", "do it", "confirm", "allow")
_NO = ("ne", "ne hvala", "preklici", "preklic", "odnehaj", "pozabi", "stop",
       "no", "cancel", "deny")


def _words(text: str) -> str:
    return " ".join(fold(text).replace(",", " ").split())


def _is_yes(text: str) -> bool:
    words = _words(text)
    return any(words == w or words.startswith(w + " ") for w in _YES)


def _is_no(text: str) -> bool:
    words = _words(text)
    return any(words == w or words.startswith(w + " ") for w in _NO)


def _human_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _human_uptime(seconds: float) -> str:
    if not seconds:
        return "neznano"
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} dni {hours} ur"
    if hours:
        return f"{hours} ur {minutes} min"
    return f"{minutes} min"


class AutonomyService:
    def __init__(self, store: Store | None = None, cfg: dict | None = None,
                 ctl: str | None = None, dry_run: bool = False,
                 logger=None):
        raw = dict(cfg or load_config())
        self.auto_cfg = {**DEFAULT_AUTONOMY, **(raw.get("autonomy") or {})}
        raw["autonomy"] = self.auto_cfg
        self.cfg = raw
        self._owns_store = store is None
        self.store = store or Store(db_path(self.cfg),
                                    privacy_cfg=self.cfg.get("privacy") or {})
        self.dry_run = bool(dry_run)
        self.log = logger or (lambda msg: print(f"[mia-auto] {msg}", flush=True))
        self.ctl = ctl or find_ctl()
        self.planner = Planner(self.store, cfg=self.cfg, ctl=self.ctl,
                               dry_run=self.dry_run, logger=self.log)
        self.scheduler = Scheduler(self.store, self.planner,
                                   lambda: self.profile(), cfg=self.cfg,
                                   logger=self.log)
        self._profile = None
        self._health: dict | None = None
        self._health_ts = 0.0
        self._recovered = False
        self._register_internals()

    def set_speak(self, callback) -> None:
        """Let the server speak scheduled reminders through connected HUDs."""
        self.planner.on_speak = callback

    # -------------------------------------------------------------- plumbing
    def _register_internals(self) -> None:
        self.planner.register("autonomy_report", self._internal_report)
        self.planner.register("profile_refresh", self._internal_profile)
        self.planner.register("scheduler_tick", self._internal_tick)

    def _internal_report(self, **kw) -> dict:
        return {"ok": True, "status": self.status()}

    def _internal_profile(self, **kw) -> dict:
        profile = self.refresh_profile()
        return {"ok": True, "summary": profile.summary(),
                "adaptation": profile.adaptation()}

    def _internal_tick(self, **kw) -> dict:
        return {"ok": True, "result": self.tick()}

    def close(self) -> None:
        if self._owns_store:
            self.store.close()

    # --------------------------------------------------------------- profile
    def profile(self, refresh: bool = False):
        if refresh or self._profile is None:
            self._profile = get_profile(refresh=refresh)
        return self._profile

    def refresh_profile(self, save: bool = True) -> Any:
        profile = get_profile(refresh=True)
        previous = self.store.load_profile()
        changes = profile.diff(previous["data"] if previous else None)
        if save:
            try:
                self.store.save_profile(profile.data, profile.fingerprint,
                                        changes)
                if changes and not changes.get("first_run") and \
                        changes.get("changed") is not False:
                    self.store.add_event("profile", profile.fingerprint,
                                         {"changes": changes})
            except Exception as exc:
                self.log(f"profile save failed: {exc}")
        self._profile = profile
        return profile

    def adaptation(self, apply: bool = False) -> dict:
        profile = self.refresh_profile()
        items = profile.adaptation()
        if not apply or not items:
            return {"ok": True, "applied": False, "items": items,
                    "summary": profile.summary()}
        policy = self.planner.autonomy_policy()
        if not policy.get("auto_install", False):
            return {"ok": False, "applied": False, "items": items,
                    "error": "autonomy.auto_install is disabled"}
        packages: list[str] = []
        for item in items:
            if item.get("installable"):
                packages.extend(p for p in item.get("packages") or []
                                if p not in packages)
        if not packages:
            return {"ok": False, "applied": False, "items": items,
                    "error": "no installable packages for this system"}
        plan = make_plan([{"kind": "ctl", "label": "namesti manjkajoča orodja",
                           "action": ["pkg", "install", *packages], "yes": True,
                           "expect": {}, "retries": 0, "timeout": 900,
                           "on_fail": "abort", "undo": [],
                           "require_verified": False}],
                         name="prilagoditev sistema", destructive=True,
                         confirmed=True)
        result = self.planner.execute(plan, name="prilagoditev sistema",
                                      source="adaptation")
        return {"ok": result.get("ok"), "applied": True, "items": items,
                "packages": packages, "task_id": result.get("task_id"),
                "result": result}

    # ----------------------------------------------------------- text entry
    def handle(self, text: str, conversation: str = "mia-main",
               source: str = "chat") -> dict | None:
        raw = (text or "").strip()
        if not raw:
            return None
        key = f"pending:{conversation}"
        pending = self.store.get_pending(key)
        if pending:
            if _is_yes(raw):
                self.store.delete_pending(key)
                data = pending.get("action") or {}
                intent = _intent_from_dict(data.get("intent") or {})
                if intent is None:
                    return {"text": "Tega ne znam več ponoviti, šefe.",
                            "tools": [], "intent": "confirm", "ok": False}
                return self.execute_intent(intent, conversation=conversation,
                                           source=source, confirmed=True)
            if _is_no(raw) or _words(raw) in ("ustavi", "ne izvrsi"):
                self.store.delete_pending(key)
                self.store.add_event("pending", key, {"action": "cancelled"})
                return {"text": "V redu, preklicano.", "tools": [],
                        "intent": "cancel", "ok": True}
            # A new command while something is pending supersedes it.
            self.store.delete_pending(key)
            self.store.add_event("pending", key,
                                 {"action": "superseded", "by": raw[:120]})
        intent = route(raw)
        if intent is None:
            return None
        return self.execute_intent(intent, conversation=conversation,
                                   source=source)

    def execute_intent(self, intent: Intent, *, conversation: str = "mia-main",
                       source: str = "chat", confirmed: bool = False) -> dict:
        if intent.kind == "confirm":
            return {"text": "Nič ne čaka na potrditev, šefe.", "tools": [],
                    "intent": "confirm", "ok": True}
        if intent.kind == "cancel":
            return {"text": "V redu.", "tools": [], "intent": "cancel",
                    "ok": True}
        if intent.kind == "help":
            return {"text": route_help(), "tools": [], "intent": "help",
                    "ok": True}
        if intent.kind == "query":
            return self._query(intent, conversation=conversation,
                               source=source)
        if intent.kind == "schedule":
            return self._schedule(intent, conversation=conversation)
        if intent.kind == "cancel_job":
            return self._cancel_job(intent)
        if intent.kind == "plan":
            return self._plan(intent, conversation=conversation, source=source,
                              confirmed=confirmed)
        if intent.kind == "action":
            if intent.confirmation and not confirmed:
                return self._ask(intent, conversation, source)
            return self._action(intent, conversation=conversation,
                                source=source, confirmed=confirmed)
        return {"text": "Tega ne razumem, šefe.", "tools": [],
                "intent": intent.name, "ok": False}

    def _ask(self, intent: Intent, conversation: str, source: str) -> dict:
        key = f"pending:{conversation}"
        self.store.set_pending(key, {"kind": "intent", "intent": intent.__dict__,
                                     "source": source},
                               prompt=intent.reply, ttl=600)
        return {"text": intent.reply or "Naj izvedem? Potrdi s »ja«.",
                "tools": [], "intent": intent.name, "ok": True,
                "pending": True}

    # ------------------------------------------------------------------ ctl
    def _ctl(self, action: list[str], *, yes: bool = False,
             timeout: float | None = None) -> dict:
        argv = ctl_argv(self.ctl) + [str(x) for x in action] + ["--json"]
        if yes:
            argv.append("--yes")
        if self.dry_run:
            argv.append("--dry-run")
        limit = timeout or _timeout_for(action)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=limit, env=dict(os.environ))
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout", "rc": 5, "data": None}
        except OSError as exc:
            return {"ok": False, "error": str(exc), "rc": 5, "data": None}
        try:
            payload = json.loads(proc.stdout or "{}")
        except ValueError:
            payload = {"ok": proc.returncode == 0,
                       "data": (proc.stdout or "").strip()[:2000]}
        payload.setdefault("rc", proc.returncode)
        if not payload.get("ok"):
            payload["error"] = str(payload.get("error") or
                                   (proc.stderr or "").strip())[:400]
        else:
            try:
                from .. import capabilities as capability_core
                capability_core.mark_learned(self.store, " ".join(action), True)
            except Exception:
                pass
        return payload

    def _tool(self, name: str, action: list[str]) -> dict:
        return {"name": name, "preview": " ".join(str(x) for x in action)[:160]}

    # ---------------------------------------------------------------- query
    def _query(self, intent: Intent, *, conversation: str,
               source: str) -> dict:
        name = intent.name
        if name in ("time", "date"):
            return {"text": intent.reply or "—", "tools": [],
                    "intent": name, "ok": True}
        if name == "resources":
            return self._query_resources()
        if name == "sysinfo":
            return self._query_sysinfo()
        if name == "health":
            return self._query_health()
        if name == "capabilities":
            return self._query_capabilities()
        if name == "jobs":
            return self._query_jobs()
        if name == "tasks":
            return self._query_tasks()
        if name == "alerts":
            return self._query_alerts()
        return {"text": "Tega ne znam odgovoriti.", "tools": [],
                "intent": name, "ok": False}

    def _query_resources(self) -> dict:
        try:
            m = self.profile().metrics()
        except Exception as exc:
            return {"text": f"Virov ne morem prebrati: {exc}", "tools": [],
                    "intent": "resources", "ok": False}
        pieces = [f"CPU {m.get('cpu_percent', 0):.0f}%",
                  f"RAM {m.get('mem_used_percent', 0):.0f}%",
                  f"disk {m.get('disk_root', {}).get('percent', 0):.0f}% zaseden"]
        battery = m.get("battery") or {}
        if battery.get("present") and m.get("battery_percent") is not None:
            pieces.append(f"baterija {m['battery_percent']}%")
        temp = m.get("max_temp_c")
        if temp is not None:
            pieces.append(f"{temp:.0f} stopinj")
        return {"text": ", ".join(pieces) + ".", "tools": [],
                "intent": "resources", "ok": True, "data": m}

    def _query_sysinfo(self) -> dict:
        p = self.profile()
        d = p.data
        osinfo = d.get("os") or {}
        cpu = d.get("cpu") or {}
        memory = d.get("memory") or {}
        desktop = d.get("desktop") or {}
        text = (f"{osinfo.get('distro_name') or osinfo.get('system')}, "
                f"jedro {osinfo.get('kernel')}, {cpu.get('cores')} jeder "
                f"{cpu.get('model') or ''}, "
                f"{_human_bytes(memory.get('total') or 0)} RAM, "
                f"namizje {desktop.get('kind')}.")
        return {"text": text, "tools": [], "intent": "sysinfo", "ok": True,
                "data": p.data}

    def _query_health(self) -> dict:
        report = self.health(force=True)
        try:
            health_mod.watch(self.store, report)
        except Exception:
            pass
        return {"text": report.get("summary") or "—", "tools": [],
                "intent": "health", "ok": report.get("level") != "critical",
                "data": report}

    def _query_capabilities(self) -> dict:
        p = self.profile()
        score = p.data.get("score") or {}
        missing = [item for item in p.readiness() if item["status"] != "ready"]
        if missing:
            first = missing[0]
            hint = first.get("hint") or ""
            text = (f"Pripravljena sem na {score.get('percent', 0)} odstotkov. "
                    f"Manjka mi {first['label'].lower()}. {hint}")
        else:
            text = "Vse, kar potrebujem na tem računalniku, je na voljo."
        return {"text": text, "tools": [], "intent": "capabilities",
                "ok": True, "data": p.data.get("score")}

    def _query_jobs(self) -> dict:
        status = self.scheduler.status()
        jobs = status.get("jobs") or []
        if not jobs:
            return {"text": "Nimam še nobenega opravila ali pravila.",
                    "tools": [], "intent": "jobs", "ok": True, "data": status}
        lines = [f"{j['name']} — {j['trigger']}" for j in jobs[:6]]
        return {"text": "Imam " + "; ".join(lines) + ".",
                "tools": [], "intent": "jobs", "ok": True, "data": status}

    def _query_tasks(self) -> dict:
        tasks = self.store.list_tasks(limit=10)
        if not tasks:
            return {"text": "Nobene naloge še ni bilo.", "tools": [],
                    "intent": "tasks", "ok": True, "data": tasks}
        last = tasks[0]
        text = (f"Zadnja naloga: {last.get('name')}, "
                f"stanje {last.get('status')}.")
        return {"text": text, "tools": [], "intent": "tasks", "ok": True,
                "data": tasks}

    def _query_alerts(self) -> dict:
        alerts = self.store.list_alerts(limit=10, acknowledged=False)
        if not alerts:
            return {"text": "Ni novih opozoril.", "tools": [],
                    "intent": "alerts", "ok": True, "data": alerts}
        text = "; ".join(a.get("message") or "" for a in alerts[:3])
        return {"text": "Opozorila: " + text, "tools": [], "intent": "alerts",
                "ok": True, "data": alerts}

    # --------------------------------------------------------------- action
    def _action(self, intent: Intent, *, conversation: str,
                source: str, confirmed: bool) -> dict:
        verb = intent.verb
        args = dict(intent.args)
        try:
            handler = getattr(self, f"_act_{verb}", None)
            if handler is None:
                return {"text": "Tega dejanja še ne znam.", "tools": [],
                        "intent": intent.name, "ok": False}
            result = handler(args, confirmed=confirmed)
            result.setdefault("intent", intent.name)
            if result.get("ok") and not result.get("text"):
                result["text"] = intent.reply or "Narejeno."
            if not result.get("ok"):
                result["text"] = self._failure_text(result, intent)
            return result
        except Exception as exc:
            self.log(f"action {verb} failed: {exc}")
            return {"text": f"Ni uspelo: {exc}", "tools": [],
                    "intent": intent.name, "ok": False}

    @staticmethod
    def _failure_text(result: dict, intent: Intent) -> str:
        error = str(result.get("error") or "").lower()
        if "not installed" in error or "requires" in error and "install" in error:
            return "Za to dejanje mi manjka orodje. Poglej prilagoditev v HUD-u."
        if "denied" in error or "policy" in error:
            return "Politika mi tega ne dovoli, šefe."
        if intent.reply:
            return f"Ni uspelo. {result.get('error') or ''}".strip()
        return f"Ni uspelo: {result.get('error') or 'neznana napaka'}"

    # ----- volume / brightness / media
    def _act_volume(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "status"
        argv = ["volume", action]
        if args.get("value") is not None:
            argv.append(str(args["value"]))
        payload = self._ctl(argv)
        if not payload.get("ok"):
            return payload
        if action == "status":
            data = payload.get("data") or {}
            text = f"Glasnost je {data.get('percent', 'neznana')} odstotkov."
        else:
            text = "Glasnost nastavljena."
        return {"ok": True, "text": text,
                "tools": [self._tool("mia-ctl", argv)],
                "data": payload.get("data")}

    def _act_brightness(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "status"
        argv = ["brightness", action]
        if args.get("value") is not None:
            argv.append(str(args["value"]))
        payload = self._ctl(argv)
        return {**payload, "tools": [self._tool("mia-ctl", argv)],
                "text": "Svetlost nastavljena." if payload.get("ok") else ""}

    def _act_media(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "status"
        payload = self._ctl(["media", action])
        text = "Predvajanje." if payload.get("ok") else ""
        if action == "status" and payload.get("ok"):
            data = payload.get("data") or {}
            text = (f"Predvaja se {data.get('title')}." if data.get("title")
                    else "Nič ne predvajam.")
        return {**payload, "text": text,
                "tools": [self._tool("mia-ctl", ["media", action])]}

    # ----- power / screenshot / clipboard
    def _act_power(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "lock"
        payload = self._ctl(["power", action], yes=action != "lock")
        return {**payload, "tools": [self._tool("mia-ctl", ["power", action])],
                "text": {"lock": "Zaklenjeno.", "suspend": "V spanje.",
                         "reboot": "Ponovni zagon.", "shutdown": "Ugasnjeno."
                         }.get(action, "Narejeno.") if payload.get("ok") else ""}

    def _act_screenshot(self, args: dict, *, confirmed: bool) -> dict:
        payload = self._ctl(["screenshot"])
        path = ""
        if isinstance(payload.get("data"), dict):
            path = payload["data"].get("path") or ""
        return {**payload, "text": f"Posnetek shranjen v {path}." if path else "",
                "tools": [self._tool("mia-ctl", ["screenshot"])]}

    def _act_clipboard(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "get"
        if action == "set":
            payload = self._ctl(["clipboard", "set", str(args.get("text") or "")])
            return {**payload, "text": "Kopirano.",
                    "tools": [self._tool("mia-ctl", ["clipboard", "set"])]}
        payload = self._ctl(["clipboard", "get"])
        text = ""
        if isinstance(payload.get("data"), dict):
            text = str(payload["data"].get("text") or "")
        spoken = f"V odložišču je: {text[:300]}" if text else "Odložišče je prazno."
        return {**payload, "text": spoken,
                "tools": [self._tool("mia-ctl", ["clipboard", "get"])]}

    # ----- open / apps / windows
    def _act_open(self, args: dict, *, confirmed: bool) -> dict:
        target = str(args.get("target") or "browser")
        payload = self._ctl(["open", target])
        return {**payload, "text": "Odprto.",
                "tools": [self._tool("mia-ctl", ["open", target])]}

    def _act_apps(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "launch"
        name = str(args.get("name") or "")
        if not name:
            return {"ok": False, "error": "manjka ime aplikacije"}
        payload = self._ctl(["apps", action, name])
        text = f"Odprla sem {name}." if action == "launch" else f"Zaprla sem {name}."
        return {**payload, "text": text if payload.get("ok") else "",
                "tools": [self._tool("mia-ctl", ["apps", action, name])]}

    def _find_window(self, name: str) -> dict | None:
        payload = self._ctl(["windows", "list"])
        windows = payload.get("data") or []
        needle = fold(name)
        for window in windows:
            hay = fold(f"{window.get('app') or ''} {window.get('title') or ''}")
            if needle and needle in hay:
                return window
        return None

    def _act_window(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "list"
        name = str(args.get("name") or "")
        if action == "list":
            payload = self._ctl(["windows", "list"])
            windows = payload.get("data") or []
            if not windows:
                return {**payload, "text": "Nobeno okno ni odprto."}
            lines = [f"{w.get('app') or ''} — {w.get('title') or ''}".strip(" —")
                     for w in windows[:6]]
            return {**payload, "text": "Odprta okna: " + "; ".join(lines) + ".",
                    "tools": [self._tool("mia-ctl", ["windows", "list"])]}
        if action == "close_all":
            payload = self._ctl(["windows", "list"])
            closed = 0
            for window in (payload.get("data") or []):
                ref = window.get("id")
                if ref:
                    self._ctl(["windows", "close", str(ref)])
                    closed += 1
            return {"ok": True, "text": f"Zaprla sem {closed} oken.",
                    "tools": [self._tool("mia-ctl", ["windows", "close"])]}
        window = self._find_window(name) if name else None
        if not window and action in ("focus", "minimize", "maximize"):
            launch = self._ctl(["apps", "launch", name]) if name else {"ok": False}
            if launch.get("ok"):
                time.sleep(1.2)
                window = self._find_window(name)
        if not window:
            return {"ok": False, "error": f"ne najdem okna {name!r}"}
        ref = str(window.get("id"))
        payload = self._ctl(["windows", action, ref])
        return {**payload, "text": "Narejeno.",
                "tools": [self._tool("mia-ctl", ["windows", action, ref])]}

    # ----- process / service
    def _act_process(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "list"
        if action == "list":
            payload = self._ctl(["process", "list"])
            procs = payload.get("data") or []
            top = procs[:3]
            text = "; ".join(f"{p.get('name')} {p.get('cpu', 0)}%" for p in top)
            return {**payload, "text": f"Najbolj obremenjujejo: {text}.",
                    "tools": [self._tool("mia-ctl", ["process", "list"])]}
        if action == "find":
            payload = self._ctl(["process", "find", str(args.get("name") or "")])
            procs = payload.get("data") or []
            if not procs:
                return {**payload, "text": "Tega procesa ne vidim."}
            text = ", ".join(f"{p.get('name')} ({p.get('pid')})" for p in procs[:4])
            return {**payload, "text": f"Našla sem: {text}.",
                    "tools": [self._tool("mia-ctl", ["process", "find"])]}
        name = str(args.get("name") or "")
        payload = self._ctl(["process", "find", name])
        procs = payload.get("data") or []
        if not procs:
            return {"ok": False, "error": f"proces {name} ne teče"}
        pid = procs[0].get("pid")
        payload = self._ctl(["process", "kill", str(pid)], yes=True)
        return {**payload, "text": f"Ustavila sem {name}.",
                "tools": [self._tool("mia-ctl", ["process", "kill", str(pid)])]}

    def _act_service(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "status"
        unit = str(args.get("unit") or "")
        if not unit:
            return {"ok": False, "error": "manjka ime storitve"}
        payload = self._ctl(["service", action, unit],
                            yes=action in ("stop", "restart", "start"))
        text = {"status": f"Storitev {unit} deluje."
                if (payload.get("data") or {}).get("active")
                else f"Storitev {unit} ne deluje.",
                "start": f"Storitev {unit} zagnana.",
                "stop": f"Storitev {unit} ustavljena.",
                "restart": f"Storitev {unit} ponovno zagnana."}.get(action, "")
        return {**payload, "text": text if payload.get("ok") else "",
                "tools": [self._tool("mia-ctl", ["service", action, unit])]}

    # ----- files / network / packages
    def _act_files(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "recent"
        if action == "search":
            payload = self._ctl(["files", "search", str(args.get("query") or "")])
            found = payload.get("data") or []
            if not found:
                return {**payload, "text": "Ničesar nisem našla."}
            text = "; ".join(Path(f.get("path", "")).name for f in found[:4])
            return {**payload, "text": f"Našla sem: {text}.",
                    "tools": [self._tool("mia-ctl", ["files", "search"])]}
        if action == "recent":
            payload = self._ctl(["files", "recent"])
            found = payload.get("data") or []
            text = "; ".join(Path(f.get("path", "")).name for f in found[:4])
            return {**payload, "text": f"Nedavne datoteke: {text}."
                    if text else "Ni nedavnih datotek."}
        if action == "open":
            payload = self._ctl(["files", "open", str(args.get("path") or "")])
            return {**payload, "text": "Odprto."}
        if action == "mkdir":
            path = str(args.get("path") or "")
            payload = self._ctl(["files", "mkdir", path])
            return {**payload, "text": f"Mapa {path} je pripravljena.",
                    "tools": [self._tool("mia-ctl", ["files", "mkdir", path])]}
        if action in ("copy", "move", "rename"):
            src, dst = str(args.get("src") or ""), str(args.get("dst") or "")
            payload = self._ctl(["files", action, src, dst], yes=True)
            verb = {"copy": "Kopirano", "move": "Premaknjeno",
                    "rename": "Preimenovano"}[action]
            return {**payload, "text": f"{verb}.",
                    "tools": [self._tool("mia-ctl", ["files", action, src, dst])]}
        if action == "trash":
            path = str(args.get("path") or "")
            payload = self._ctl(["files", "trash", path], yes=True)
            return {**payload, "text": f"{path} je v smeteh.",
                    "tools": [self._tool("mia-ctl", ["files", "trash", path])]}
        if action == "delete":
            path = str(args.get("path") or "")
            payload = self._ctl(["files", "delete", path], yes=True)
            return {**payload, "text": f"{path} je izbrisan.",
                    "tools": [self._tool("mia-ctl", ["files", "delete", path])]}
        if action == "archive":
            src, dst = str(args.get("src") or ""), str(args.get("dst") or "")
            payload = self._ctl(["files", "archive", src, dst])
            return {**payload, "text": f"Arhiv {dst} je pripravljen.",
                    "tools": [self._tool("mia-ctl", ["files", "archive", src, dst])]}
        if action == "extract":
            archive = str(args.get("archive") or "")
            dest = str(args.get("dest") or "")
            payload = self._ctl(["files", "extract", archive, dest])
            return {**payload, "text": f"Razširjeno v {dest}.",
                    "tools": [self._tool("mia-ctl", ["files", "extract", archive, dest])]}
        if action == "du":
            payload = self._ctl(["files", "du", str(args.get("path") or "~")])
            data = payload.get("data") or {}
            return {**payload, "text": f"Velikost je {_human_bytes(data.get('bytes', 0))}."}
        if action == "large":
            result = self.planner._scan_large(min_mb=500, limit=8)
            files = result.get("files") or []
            if not files:
                return {"ok": True, "text": "Ni velikih datotek.", "data": result}
            biggest = files[0]
            text = (f"Največja je {Path(biggest['path']).name}, "
                    f"{_human_bytes(biggest['size'])}.")
            return {"ok": True, "text": text, "data": result}
        return {"ok": False, "error": f"neznana datotečna akcija {action}"}

    def _act_net(self, args: dict, *, confirmed: bool) -> dict:
        if args.get("action") == "wifi-list":
            payload = self._ctl(["net", "wifi", "list"])
            rows = payload.get("data") or []
            text = ", ".join(str(r.get("ssid") or r) for r in rows[:8]) or "Ni omrežij."
            return {**payload, "text": f"Vidim: {text}.",
                    "tools": [self._tool("mia-ctl", ["net", "wifi", "list"])]}
        if args.get("action") in ("enable", "disable"):
            action = str(args["action"])
            payload = self._ctl(["net", "firewall", action], yes=True)
            return {**payload, "text": f"Požarni zid {action}.",
                    "tools": [self._tool("mia-ctl", ["net", "firewall", action])]}
        if args.get("ssid"):
            argv = ["net", "wifi", "connect", str(args["ssid"])]
            if args.get("password"):
                argv.append(str(args["password"]))
            payload = self._ctl(argv)
            return {**payload, "text": f"Povezujem se na {args['ssid']}.",
                    "tools": [self._tool("mia-ctl", ["net", "wifi", "connect"])]}
        if args.get("host"):
            payload = self._ctl(["net", "ping", str(args["host"])])
            return {**payload, "text": f"Ping {args['host']} končan."}
        payload = self._ctl(["net", "status"])
        data = payload.get("data") or {}
        addresses = data.get("addresses") or data.get("ips") or [""]
        ip = addresses[0] if addresses else ""
        wifi = data.get("wifi")
        ssid = ""
        if isinstance(wifi, dict):
            ssid = str(wifi.get("ssid") or "")
        elif isinstance(wifi, list) and wifi:
            ssid = str(wifi[0])
        ssid = ssid or str(data.get("ssid") or "")
        text = f"IP {ip}." if ip else "Ni omrežja."
        if ssid:
            text += f" Wi-Fi {ssid}."
        return {**payload, "text": text,
                "tools": [self._tool("mia-ctl", ["net", "status"])]}

    def _act_pkg(self, args: dict, *, confirmed: bool) -> dict:
        action = args.get("action") or "list-upgradable"
        if action in ("install", "remove"):
            packages = [str(p) for p in (args.get("packages") or []) if p]
            if not packages:
                return {"ok": False, "error": "manjka ime paketa"}
            payload = self._ctl(["pkg", action, *packages], yes=True)
            verb = "namestila" if action == "install" else "odstranila"
            return {**payload, "text": f"Paket sem {verb}.",
                    "tools": [self._tool("mia-ctl", ["pkg", action, *packages])]}
        if action == "search":
            payload = self._ctl(["pkg", "search", str(args.get("query") or "")])
            rows = payload.get("data") or []
            text = "; ".join(str(r.get("name") or r) for r in rows[:4]) or "Ni zadetkov."
            return {**payload, "text": f"Našla sem: {text}."}
        payload = self._ctl(["pkg", action])
        data = payload.get("data") or {}
        if action == "list-upgradable":
            count = data.get("count") if isinstance(data, dict) else len(data or [])
            text = f"{count} posodobitev je na voljo." if count else "Sistem je posodobljen."
        else:
            text = "Posodobitve pripravljene."
        return {**payload, "text": text,
                "tools": [self._tool("mia-ctl", ["pkg", action])]}

    # ---------------------------------------------------------------- plans
    def _plan(self, intent: Intent, *, conversation: str, source: str,
              confirmed: bool) -> dict:
        template = intent.args.get("template")
        if not template:
            return {"text": "Načrta ne poznam.", "tools": [],
                    "intent": intent.name, "ok": False}
        try:
            plan = build_template(template, self.profile())
        except Exception as exc:
            return {"text": f"Načrta ne morem sestaviti: {exc}", "tools": [],
                    "intent": intent.name, "ok": False}
        if plan.get("destructive") and not confirmed and \
                not self.planner.destructive_allowed():
            return self._ask(intent, conversation, source)
        plan["confirmed"] = True
        result = self.planner.execute(plan, name=plan.get("name") or template,
                                      source=source, origin=conversation)
        ok = bool(result.get("ok"))
        text = intent.reply or ("Načrt izveden." if ok else "Načrt ni uspel.")
        if not ok:
            text = f"Načrt se je ustavil: {result.get('error') or 'napaka'}."
        return {"text": text, "tools": [],
                "intent": intent.name, "ok": ok,
                "task_id": result.get("task_id"), "data": result}

    # ------------------------------------------------------------- schedule
    def _schedule(self, intent: Intent, *, conversation: str) -> dict:
        trigger = intent.trigger or {"kind": "every", "seconds": 3600}
        body = str(intent.args.get("body") or intent.args.get("name") or "Opomnik")
        if intent.verb == "rule":
            if intent.args.get("cleanup"):
                plan = build_template("cleanup")
                plan["confirmed"] = True
            else:
                plan = plan_for_reminder(body)
            kind = "rule"
        else:
            plan = plan_for_reminder(body)
            kind = "job"
        job_id = self.scheduler.add_job(
            str(intent.args.get("name") or body[:60]), trigger, plan,
            conditions=[], kind=kind, source="voice")
        self.store.add_event("job", f"#{job_id}",
                             {"created": trigger_summary(trigger),
                              "body": body[:200]})
        text = intent.reply or "Opravilo shranjeno."
        return {"text": text, "tools": [],
                "intent": intent.name, "ok": True,
                "job_id": job_id, "data": {"trigger": trigger,
                                           "summary": trigger_summary(trigger)}}

    def _cancel_job(self, intent: Intent) -> dict:
        job_id = int(intent.args.get("job_id") or 0)
        if not job_id:
            return {"text": "Katero opravilo naj prekličem?", "tools": [],
                    "intent": intent.name, "ok": False}
        ok = self.scheduler.remove_job(job_id)
        return {"text": f"Opravilo {job_id} preklicano." if ok
                else f"Opravila {job_id} ne najdem.",
                "tools": [], "intent": intent.name, "ok": ok}

    # --------------------------------------------------------------- health
    def health(self, force: bool = False) -> dict:
        now = time.time()
        if force or self._health is None or now - self._health_ts > 120:
            self._health = health_mod.check(self.profile(), self.cfg, self.store)
            self._health_ts = now
        return self._health

    def remediate(self, *, force: bool = False) -> dict:
        report = self.health(force=force)
        return health_mod.remediate(report, self.planner, self.cfg,
                                    dry_run=self.dry_run)

    # ----------------------------------------------------------- background
    def tick(self, *, execute: bool = True, health: bool = True) -> dict:
        if not self._recovered:
            recovered = self.store.recover_tasks()
            self.store.purge_pending()
            if recovered:
                self.log(f"recovered {recovered} interrupted tasks")
            self._recovered = True
        result: dict[str, Any] = {"ts": time.time(),
                                  "scheduler": self.scheduler.tick(
                                      execute=execute,
                                      max_jobs=int(self.auto_cfg.get(
                                          "max_jobs_per_tick", 3)))}
        if health and time.time() - self._health_ts > float(
                self.auto_cfg.get("health_interval", 300)):
            report = self.health(force=True)
            try:
                created = health_mod.watch(self.store, report)
            except Exception:
                created = []
            result["health"] = {"level": report.get("level"),
                                "score": report.get("score"),
                                "alerts": created}
            auto = bool(self.auto_cfg.get("auto_remediate", False))
            if auto and report.get("level") in ("warn", "critical"):
                result["remediation"] = self.remediate()
        return result

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        profile = self.profile()
        if self._health is None:
            try:
                self._health = self.health()
            except Exception:
                pass
        report = self._health or {}
        tasks = self.store.list_tasks(limit=10)
        return {
            "profile": {"summary": profile.summary(),
                        "fingerprint": profile.fingerprint,
                        "data": profile.data},
            "score": profile.data.get("score"),
            "health": {"level": report.get("level"), "score": report.get("score"),
                       "summary": report.get("summary")} if report else {},
            "scheduler": self.scheduler.status(),
            "tasks": [{"id": t["id"], "name": t.get("name"),
                       "status": t.get("status"), "created": t.get("created")}
                      for t in tasks],
            "pending": self.store.list_pending(limit=20),
            "alerts": self.store.list_alerts(limit=20, acknowledged=False),
            "adaptation": profile.adaptation(),
            "policy": self.planner.autonomy_policy(),
        }


def _timeout_for(action: list[str]) -> float:
    first = str(action[0]) if action else ""
    if first == "pkg":
        second = str(action[1]) if len(action) > 1 else ""
        if second in ("upgrade", "update", "install", "remove"):
            return 1800
        if second in ("search", "list-upgradable"):
            return 180
    if first in ("files", "process", "windows", "net"):
        return 60
    return 30


def _intent_from_dict(data: dict) -> Intent | None:
    if not isinstance(data, dict):
        return None
    try:
        return Intent(name=str(data.get("name") or "unknown"),
                      kind=str(data.get("kind") or "action"),
                      verb=str(data.get("verb") or ""),
                      args=data.get("args") or {},
                      reply=str(data.get("reply") or ""),
                      confirmation=bool(data.get("confirmation")),
                      destructive=bool(data.get("destructive")),
                      trigger=data.get("trigger"),
                      confidence=float(data.get("confidence") or 0.9),
                      text=str(data.get("text") or ""))
    except (TypeError, ValueError):
        return None
