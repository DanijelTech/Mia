"""Declarative conditions used by jobs, rules, probes and wait steps.

A condition is plain JSON so it can be stored in SQLite, produced by the agent
and explained in the HUD. No shell, no eval: only a fixed vocabulary of
metrics and operators.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

OPS = ("<", "<=", ">", ">=", "==", "!=", "contains", "startswith")


def _compare(left: Any, op: str, right: Any) -> bool:
    try:
        if op == "contains":
            return str(right) in str(left)
        if op == "startswith":
            return str(left).startswith(str(right))
        left_n, right_n = float(left), float(right)
        return {"<": left_n < right_n, "<=": left_n <= right_n,
                ">": left_n > right_n, ">=": left_n >= right_n,
                "==": left_n == right_n, "!=": left_n != right_n,
                }.get(op, False)
    except (TypeError, ValueError):
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        return False


def _service_active(unit: str) -> bool:
    if not shutil.which("systemctl"):
        return False
    try:
        proc = subprocess.run(["systemctl", "is-active", unit],
                              capture_output=True, text=True, timeout=4)
        return proc.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def _metric(metrics: dict, path: str, default: Any = None) -> Any:
    node: Any = metrics
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def evaluate(condition: Any, metrics: dict | None = None,
             profile: Any = None) -> tuple[bool, dict]:
    """Return (result, details). Unknown shapes fail closed with a reason."""
    if not condition:
        return True, {"condition": None, "result": True, "reason": "always"}
    metrics = metrics or {}
    if isinstance(condition, list):
        results = [evaluate(item, metrics, profile) for item in condition]
        ok = all(r[0] for r in results)
        return ok, {"op": "all", "items": [r[1] for r in results]}
    if not isinstance(condition, dict):
        return False, {"reason": "invalid condition"}

    if "all" in condition:
        results = [evaluate(item, metrics, profile) for item in condition["all"]]
        return all(r[0] for r in results), {"op": "all",
                                            "items": [r[1] for r in results]}
    if "any" in condition:
        results = [evaluate(item, metrics, profile) for item in condition["any"]]
        return any(r[0] for r in results), {"op": "any",
                                            "items": [r[1] for r in results]}
    if "not" in condition:
        ok, detail = evaluate(condition["not"], metrics, profile)
        return (not ok), {"op": "not", "item": detail}

    metric = condition.get("metric")
    if metric:
        op = str(condition.get("op", "=="))
        expected = condition.get("value")
        if metric == "path_free_percent":
            path = condition.get("path") or "/"
            try:
                usage = shutil.disk_usage(path)
                actual = usage.free / (usage.total or 1) * 100
            except OSError:
                actual = 0.0
        elif metric == "file_age_seconds":
            path = Path(str(condition.get("path") or "")).expanduser()
            try:
                actual = max(0.0, time.time() - path.stat().st_mtime)
            except OSError:
                actual = -1.0
        else:
            actual = _metric(metrics, metric)
        if metric == "hour":
            actual = _dt.datetime.now().hour if actual is None else actual
        if metric == "weekday":
            actual = _dt.datetime.now().weekday() if actual is None else actual
        ok = actual is not None and _compare(actual, op, expected)
        return ok, {"metric": metric, "op": op, "expected": expected,
                    "actual": actual, "result": ok}

    if "hour_between" in condition:
        start, end = condition["hour_between"][:2]
        hour = _dt.datetime.now().hour
        ok = start <= hour < end if start <= end else (hour >= start or hour < end)
        return ok, {"hour_between": [start, end], "hour": hour, "result": ok}
    if "weekday_in" in condition:
        weekday = _dt.datetime.now().weekday()
        ok = weekday in list(condition["weekday_in"])
        return ok, {"weekday": weekday, "result": ok}
    if "file_exists" in condition:
        ok = Path(str(condition["file_exists"])).expanduser().exists()
        return ok, {"file_exists": str(condition["file_exists"]), "result": ok}
    if "file_older_than" in condition:
        spec = condition["file_older_than"]
        path = Path(str(spec.get("path") or "")).expanduser()
        try:
            age = time.time() - path.stat().st_mtime
            ok = age >= float(spec.get("seconds", 86400))
        except OSError:
            ok = False
            age = None
        return ok, {"path": str(path), "age": age, "result": ok}
    if "service_active" in condition:
        ok = _service_active(str(condition["service_active"]))
        return ok, {"service_active": condition["service_active"], "result": ok}
    if "wifi_connected" in condition:
        actual = bool((metrics.get("wifi_connected")))
        ok = actual == bool(condition["wifi_connected"])
        return ok, {"wifi_connected": actual, "result": ok}
    if "on_battery" in condition:
        actual = bool(metrics.get("on_battery"))
        ok = actual == bool(condition["on_battery"])
        return ok, {"on_battery": actual, "result": ok}
    if "network_up" in condition:
        actual = bool(metrics.get("network_up"))
        ok = actual == bool(condition["network_up"])
        return ok, {"network_up": actual, "result": ok}
    if "env" in condition:
        spec = condition["env"]
        actual = os.environ.get(str(spec.get("name") or ""))
        ok = _compare(actual, str(spec.get("op", "==")), spec.get("value"))
        return ok, {"env": spec.get("name"), "actual": actual, "result": ok}

    return False, {"reason": "unknown condition", "condition": condition}


def describe(condition: Any) -> str:
    if not condition:
        return "vedno"
    if isinstance(condition, list):
        return " in ".join(describe(c) for c in condition)
    if not isinstance(condition, dict):
        return str(condition)
    if "all" in condition:
        return " in ".join(describe(c) for c in condition["all"])
    if "any" in condition:
        return " ali ".join(describe(c) for c in condition["any"])
    if "not" in condition:
        return "ne (" + describe(condition["not"]) + ")"
    if "metric" in condition:
        return f"{condition['metric']} {condition.get('op', '==')} {condition.get('value')}"
    if "hour_between" in condition:
        return f"ura med {condition['hour_between'][0]} in {condition['hour_between'][1]}"
    if "weekday_in" in condition:
        return "dan v " + ",".join(str(d) for d in condition["weekday_in"])
    if "file_exists" in condition:
        return f"obstaja {condition['file_exists']}"
    if "file_older_than" in condition:
        spec = condition["file_older_than"]
        return f"{spec.get('path')} starejši od {spec.get('seconds')} s"
    if "service_active" in condition:
        return f"storitev {condition['service_active']} deluje"
    if "wifi_connected" in condition:
        return "Wi-Fi povezan" if condition["wifi_connected"] else "Wi-Fi ni povezan"
    if "on_battery" in condition:
        return "na bateriji" if condition["on_battery"] else "na napajanju"
    if "network_up" in condition:
        return "omrežje deluje" if condition["network_up"] else "omrežje ne deluje"
    return str(condition)
