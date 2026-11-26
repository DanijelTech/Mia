"""Persistent scheduler and reactive rules.

Jobs and rules are the same primitive: a trigger, optional conditions and a
plan. The difference is intent, not mechanism — a job usually runs on a clock,
a rule reacts to the machine. The engine is deliberately small:

* time triggers: `at`, `every`, `daily`
* machine triggers: `condition`, `event`, `idle`

State lives in SQLite (`jobs`, `job_runs`), so schedules survive restarts. A
condition trigger is edge-triggered by default: it fires once when the condition
has held long enough and re-arms only after the condition clears.
"""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path
from typing import Any, Callable

from .conditions import describe, evaluate
from .planner import Planner, make_plan, sanitize_plan

TRIGGER_KINDS = ("at", "every", "daily", "condition", "event", "idle")


def _next_daily(time_text: str, weekdays: list[int] | None, now: float) -> float:
    try:
        hour, minute = [int(x) for x in str(time_text).split(":", 1)]
    except (ValueError, TypeError):
        hour, minute = 8, 0
    current = _dt.datetime.fromtimestamp(now)
    for offset in range(0, 15):
        candidate = (current + _dt.timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0)
        if candidate.timestamp() <= now + 0.5:
            continue
        if weekdays and candidate.weekday() not in weekdays:
            continue
        return candidate.timestamp()
    return now + 86400


def normalize_trigger(trigger: dict | None) -> dict:
    if not isinstance(trigger, dict):
        return {"kind": "every", "seconds": 3600}
    trigger = dict(trigger)
    kind = str(trigger.get("kind") or "every")
    if kind not in TRIGGER_KINDS:
        kind = "every"
    trigger["kind"] = kind
    if kind == "every":
        trigger["seconds"] = max(5, int(float(trigger.get("seconds") or 3600)))
    elif kind == "daily":
        trigger["time"] = str(trigger.get("time") or "08:00")
        trigger["weekdays"] = [int(x) for x in (trigger.get("weekdays") or [])]
    elif kind == "at":
        trigger["ts"] = float(trigger.get("ts") or time.time())
    elif kind in ("condition", "idle"):
        trigger["for_seconds"] = max(0, int(float(trigger.get("for_seconds") or 0)))
        trigger["poll"] = max(5, int(float(trigger.get("poll") or 60)))
        trigger.setdefault("armed", True)
        trigger.setdefault("since", 0)
    elif kind == "event":
        trigger["name"] = str(trigger.get("name") or "file_changed")
        trigger["poll"] = max(5, int(float(trigger.get("poll") or 30)))
        trigger.setdefault("seen", "__unset__")
    return trigger


def next_run(trigger: dict, now: float, last_run: float | None = None) -> float | None:
    trigger = normalize_trigger(trigger)
    kind = trigger["kind"]
    if kind == "at":
        return trigger["ts"]
    if kind == "every":
        base = last_run if last_run else now
        return float(base) + float(trigger["seconds"])
    if kind == "daily":
        return _next_daily(trigger["time"], trigger.get("weekdays"), now)
    return now + float(trigger.get("poll") or 60)


def trigger_summary(trigger: dict) -> str:
    trigger = normalize_trigger(trigger)
    kind = trigger["kind"]
    if kind == "at":
        return "enkrat ob " + time.strftime("%d.%m. %H:%M",
                                            time.localtime(trigger["ts"]))
    if kind == "every":
        seconds = trigger["seconds"]
        if seconds % 3600 == 0:
            return f"vsakih {seconds // 3600} h"
        if seconds % 60 == 0:
            return f"vsakih {seconds // 60} min"
        return f"vsakih {seconds} s"
    if kind == "daily":
        days = ["pon", "tor", "sre", "čet", "pet", "sob", "ned"]
        selected = ",".join(days[d] for d in trigger.get("weekdays") or [])
        return f"vsak dan ob {trigger['time']}" + (f" ({selected})" if selected else "")
    if kind == "condition":
        return f"ko velja pogoj {trigger.get('for_seconds', 0)} s"
    if kind == "event":
        return f"ob dogodku {trigger['name']}"
    if kind == "idle":
        return f"ko je sistem prost {trigger.get('for_seconds', 0)} s"
    return str(trigger)


def _event_value(name: str, trigger: dict, metrics: dict) -> Any:
    if name == "file_changed":
        path = Path(str(trigger.get("path") or "")).expanduser()
        try:
            stat = path.stat()
            return [stat.st_mtime, stat.st_size]
        except OSError:
            return None
    if name == "file_missing":
        return not Path(str(trigger.get("path") or "")).expanduser().exists()
    if name == "service_down":
        from .conditions import _service_active
        return not _service_active(str(trigger.get("unit") or ""))
    if name == "battery_low":
        return bool(metrics.get("on_battery")) and \
            (metrics.get("battery_percent") or 100) <= float(trigger.get("value") or 15)
    if name == "network_down":
        return not bool(metrics.get("network_up"))
    return None


class Scheduler:
    def __init__(self, store, planner: Planner, profile_provider: Callable[[], Any],
                 cfg: dict | None = None,
                 logger: Callable[[str], None] | None = None):
        self.store = store
        self.planner = planner
        self.profile_provider = profile_provider
        self.cfg = cfg or {}
        self.log = logger or (lambda msg: None)
        self._last_metrics: dict = {}

    # ------------------------------------------------------------------ CRUD
    def add_job(self, name: str, trigger: dict, plan: dict, *,
                conditions: list | None = None, kind: str = "job",
                enabled: bool = True, max_runs: int = 0, source: str = "user",
                tags: list | None = None, job_id: int | None = None) -> int:
        trigger = normalize_trigger(trigger)
        clean = sanitize_plan(plan)
        now = time.time()
        nxt = next_run(trigger, now, None)
        return self.store.upsert_job(name, trigger, clean, conditions or [],
                                     kind=kind, enabled=enabled,
                                     max_runs=max_runs, source=source,
                                     tags=tags, job_id=job_id,
                                     next_run=nxt)

    def update_job(self, job_id: int, **fields: Any) -> bool:
        if "trigger" in fields:
            fields["trigger"] = normalize_trigger(fields["trigger"])
            fields["next_run"] = next_run(fields["trigger"], time.time(),
                                          fields.get("last_run"))
        return self.store.update_job(job_id, **fields)

    def remove_job(self, job_id: int) -> bool:
        return self.store.delete_job(job_id)

    def list_jobs(self, enabled: bool | None = None,
                  kind: str | None = None) -> list[dict]:
        return self.store.list_jobs(enabled=enabled, kind=kind)

    def get_job(self, job_id: int) -> dict | None:
        return self.store.get_job(job_id)

    # ------------------------------------------------------------- execution
    def _metrics(self) -> dict:
        try:
            profile = self.profile_provider()
            return profile.metrics(sample_seconds=0.05)
        except Exception as exc:
            self.log(f"metrics failed: {exc}")
            return {}

    def tick(self, now: float | None = None, *, execute: bool = True,
             max_jobs: int = 3) -> dict:
        now = time.time() if now is None else float(now)
        jobs = self.store.list_jobs(enabled=True)
        fired: list[dict] = []
        checked = 0
        metrics: dict | None = None
        for job in jobs:
            if len(fired) >= max_jobs:
                break
            checked += 1
            if job.get("max_runs") and job["run_count"] >= job["max_runs"]:
                self.store.update_job(job["id"], enabled=False,
                                      last_status="exhausted")
                continue
            trigger = normalize_trigger(job.get("trigger"))
            if metrics is None and trigger["kind"] in ("condition", "event", "idle"):
                metrics = self._metrics()
            due, detail, trigger = self._is_due(job, trigger, now, metrics or {})
            if trigger != job.get("trigger"):
                self.store.update_job(job["id"], trigger=trigger,
                                      next_run=next_run(trigger, now,
                                                        job.get("last_run")))
            if not due:
                continue
            ok, cond_detail = True, {}
            if job.get("conditions"):
                conds = job["conditions"]
                if isinstance(conds, dict):
                    conds = [conds]
                ok, cond_detail = evaluate(conds, metrics or {}, None)
            if not ok:
                self.store.update_job(job["id"], last_status="skipped",
                                      last_error="conditions not met")
                continue
            fired.append({"job": job, "detail": detail,
                          "conditions": cond_detail})
            if not execute:
                continue
            self._run_job(job, trigger, now)
        return {"checked": checked, "fired": fired,
                "count": len(fired), "ts": now}

    def _is_due(self, job: dict, trigger: dict, now: float,
                metrics: dict) -> tuple[bool, dict, dict]:
        kind = trigger["kind"]
        if kind == "at":
            return (now >= float(trigger["ts"]) and int(job["run_count"]) == 0,
                    {"at": trigger["ts"]}, trigger)
        if kind == "every":
            nxt = job.get("next_run")
            return (nxt is None or now >= float(nxt),
                    {"next_run": nxt}, trigger)
        if kind == "daily":
            nxt = job.get("next_run")
            return (nxt is None or now >= float(nxt),
                    {"next_run": nxt}, trigger)
        if kind == "event":
            value = _event_value(trigger["name"], trigger, metrics)
            seen = trigger.get("seen", "__unset__")
            if seen == "__unset__":
                # First observation only establishes the baseline; a rule must
                # fire because something changed, not because Mia just started.
                trigger["seen"] = value
                return False, {"event": trigger["name"], "value": value,
                               "baseline": True}, trigger
            changed = seen != value
            trigger["seen"] = value
            bad = value is not None and value is not False and value != [] \
                and value != [0, 0]
            return (changed and bad, {"event": trigger["name"],
                                      "value": value, "changed": changed}, trigger)
        if kind == "idle":
            busy = float(metrics.get("cpu_percent") or 0) > float(
                trigger.get("cpu_below", 15)) or \
                float((metrics.get("load") or [99])[0]) > float(
                    trigger.get("load_below", os_cpu_cores() * 0.5))
            if busy:
                trigger["since"] = 0
                trigger["armed"] = True
                return False, {"idle": False}, trigger
            if not trigger.get("since"):
                trigger["since"] = now
            held = now - float(trigger["since"])
            due = bool(trigger.get("armed", True)) and \
                held >= float(trigger.get("for_seconds") or 0)
            if due:
                trigger["armed"] = False
            return due, {"idle_seconds": held}, trigger
        # condition
        condition = trigger.get("condition") or job.get("conditions") or []
        ok, detail = evaluate(condition, metrics, None)
        if not ok:
            trigger["since"] = 0
            trigger["armed"] = True
            return False, detail, trigger
        if not trigger.get("since"):
            trigger["since"] = now
        held = now - float(trigger["since"])
        required = float(trigger.get("for_seconds") or 0)
        due = bool(trigger.get("armed", True)) and held >= required
        if due and not trigger.get("repeat", False):
            trigger["armed"] = False
        return due, {**detail, "held": held}, trigger

    def _run_job(self, job: dict, trigger: dict, now: float) -> None:
        task_id = None
        run_id = self.store.record_job_run(job["id"], None, "running",
                                           {"trigger": trigger_summary(trigger)})
        try:
            plan = dict(job.get("plan") or {})
            plan["confirmed"] = True  # the user created this automation
            outcome = self.planner.execute(
                plan, name=job.get("name") or f"job #{job['id']}",
                source="job", job_id=job["id"],
                origin=f"job:{job['id']}")
            task_id = outcome.get("task_id")
            status = "done" if outcome.get("ok") else "failed"
            error = "" if outcome.get("ok") else str(outcome.get("error") or "")
            self.store.finish_job_run(run_id, status,
                                      {"task_id": task_id,
                                       "failed_step": outcome.get("failed_step")})
            trigger = normalize_trigger(trigger)
            self.store.update_job(
                job["id"], run_count=int(job.get("run_count") or 0) + 1,
                last_run=now, last_status=status, last_error=error[:500],
                trigger=trigger,
                next_run=next_run(trigger, now, now))
            self.store.add_event("job", f"#{job['id']}",
                                 {"status": status, "task_id": task_id,
                                  "error": error[:300]})
            self.log(f"job #{job['id']} {status} (task {task_id})")
        except Exception as exc:
            self.store.finish_job_run(run_id, "failed",
                                      {"error": f"{type(exc).__name__}: {exc}"})
            self.store.update_job(job["id"], last_status="failed",
                                  last_error=f"{type(exc).__name__}: {exc}"[:500],
                                  next_run=next_run(trigger, now, now))
            self.log(f"job #{job['id']} exploded: {exc}")

    # -------------------------------------------------------------- helpers
    def describe_job(self, job: dict) -> str:
        bits = [trigger_summary(job.get("trigger") or {})]
        if job.get("conditions"):
            conds = job["conditions"]
            if isinstance(conds, dict):
                conds = [conds]
            bits.append("če " + " in ".join(describe(c) for c in conds))
        plan = job.get("plan") or {}
        bits.append(f"{len(plan.get('steps') or [])} korakov")
        return " · ".join(bits)

    def status(self) -> dict:
        jobs = self.store.list_jobs()
        return {
            "total": len(jobs),
            "enabled": sum(1 for j in jobs if j.get("enabled")),
            "rules": sum(1 for j in jobs if j.get("kind") == "rule"),
            "jobs": [{"id": j["id"], "name": j["name"], "kind": j.get("kind"),
                      "enabled": j.get("enabled"),
                      "trigger": trigger_summary(j.get("trigger") or {}),
                      "next_run": j.get("next_run"),
                      "last_status": j.get("last_status"),
                      "run_count": j.get("run_count")} for j in jobs[:50]],
        }


def os_cpu_cores() -> int:
    import os
    return os.cpu_count() or 1


def plan_for_reminder(text: str) -> dict:
    return make_plan([
        {"kind": "speak", "label": "izreci opomnik", "text": text,
         "retries": 0, "timeout": 10, "on_fail": "continue", "undo": [],
         "expect": {}, "require_verified": False},
        {"kind": "notify", "label": "opomnik", "title": "Mia",
         "body": text, "retries": 0, "timeout": 15,
         "on_fail": "continue", "undo": [], "expect": {},
         "require_verified": False},
    ], name=f"opomnik: {text[:40]}")
