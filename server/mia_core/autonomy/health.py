"""Health watchdog: detect problems, explain them, remediate the safe ones.

Checks use the same profile/metrics as everything else. Remediation is split in
two tiers: housekeeping (temp files, learning pruning, a notification) always
runs; privileged or destructive fixes only run when the user enabled
`autonomy.auto_remediate`.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

LEVELS = ("ok", "info", "warn", "critical")


def _check(key: str, title: str, level: str, message: str, *,
           value: Any = None, threshold: Any = None,
           remediation: dict | None = None, category: str = "system") -> dict:
    return {"key": key, "title": title, "level": level, "message": message,
            "value": value, "threshold": threshold,
            "remediation": remediation or {}, "category": category}


def _disk_check(key: str, label: str, free_percent: float,
                free_bytes: int) -> dict:
    level = "ok"
    if free_percent < 5:
        level = "critical"
    elif free_percent < 12:
        level = "warn"
    return _check(
        key, label, level,
        f"{free_percent:.1f}% prostega prostora ({_human(free_bytes)})",
        value=round(free_percent, 1), threshold=12,
        remediation={"template": "cleanup"} if level != "ok" else {},
        category="storage")


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _cert_days(path: Path) -> int | None:
    if not path.exists():
        return None
    if shutil.which("openssl"):
        try:
            proc = subprocess.run(
                ["openssl", "x509", "-enddate", "-noout", "-in", str(path)],
                capture_output=True, text=True, timeout=4)
            if proc.returncode == 0 and "=" in proc.stdout:
                raw = proc.stdout.strip().split("=", 1)[1]
                expiry = time.strptime(raw, "%b %d %H:%M:%S %Y %Z")
                return int((time.mktime(expiry) - time.time()) / 86400)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return None


def _failed_services() -> int:
    if not shutil.which("systemctl"):
        return 0
    try:
        proc = subprocess.run(["systemctl", "--failed", "--no-legend",
                               "--plain"], capture_output=True, text=True,
                              timeout=5)
        return len([line for line in proc.stdout.splitlines() if line.strip()])
    except (OSError, subprocess.SubprocessError):
        return 0


def check(profile: Any, cfg: dict | None = None, store: Any = None) -> dict:
    cfg = cfg or {}
    try:
        metrics = profile.metrics(sample_seconds=0.08)
    except Exception:
        metrics = {}
    checks: list[dict] = []

    root = metrics.get("disk_root") or {}
    home = metrics.get("disk_home") or {}
    if root:
        checks.append(_disk_check("disk.root", "Korenski disk",
                                  float(metrics.get("disk_free_percent") or 0),
                                  int(root.get("free") or 0)))
    if home and home.get("total") != root.get("total"):
        checks.append(_disk_check("disk.home", "Domači disk",
                                  (home.get("free", 0) / (home.get("total") or 1)) * 100,
                                  int(home.get("free") or 0)))

    used = float(metrics.get("mem_used_percent") or 0)
    level = "critical" if used > 95 else "warn" if used > 85 else "ok"
    checks.append(_check("memory.used", "Delovni pomnilnik", level,
                         f"{used:.0f}% zasedenega RAM-a",
                         value=used, threshold=85, category="memory",
                         remediation={"notify": "Pomnilnik je skoraj poln."}
                         if level != "ok" else {}))

    swap = float(metrics.get("swap_used_percent") or 0)
    checks.append(_check("memory.swap", "Swap", "warn" if swap > 70 else "ok",
                         f"{swap:.0f}% swapa", value=swap, threshold=70,
                         category="memory"))

    cores = int(metrics.get("cpu_cores") or 1)
    load1 = float((metrics.get("load") or [0])[0])
    level = "critical" if load1 > cores * 2.5 else "warn" if load1 > cores * 1.2 else "ok"
    checks.append(_check("cpu.load", "Obremenitev CPU", level,
                         f"load {load1:.2f} na {cores} jedrih",
                         value=load1, threshold=cores * 1.2, category="cpu"))

    max_temp = metrics.get("max_temp_c")
    if max_temp is not None:
        level = "critical" if max_temp >= 95 else "warn" if max_temp >= 85 else "ok"
        checks.append(_check("thermal.max", "Temperatura", level,
                             f"{max_temp:.0f} °C", value=max_temp,
                             threshold=85, category="thermal"))

    battery = metrics.get("battery") or {}
    if battery.get("present") and battery.get("percent") is not None:
        percent = int(battery["percent"])
        on_battery = bool(metrics.get("on_battery"))
        level = ("critical" if on_battery and percent <= 10 else
                 "warn" if on_battery and percent <= 20 else "ok")
        checks.append(_check("battery.level", "Baterija", level,
                             f"{percent}% ({'na bateriji' if on_battery else 'na napajanju'})",
                             value=percent, threshold=20, category="power"))

    if not metrics.get("network_up"):
        checks.append(_check("network.up", "Omrežje", "warn",
                             "Ni aktivne omrežne povezave", value=False,
                             category="network"))

    failed = _failed_services()
    if failed:
        checks.append(_check("services.failed", "Storitve", "warn",
                             f"{failed} systemd enot v napaki", value=failed,
                             remediation={"notify": "Nekatere storitve so v napaki."},
                             category="service"))

    for cert in (Path("server/certs/cert.pem"), Path.home() / ".config/mia/cert.pem"):
        days = _cert_days(cert)
        if days is not None:
            level = "critical" if days < 7 else "warn" if days < 30 else "ok"
            checks.append(_check("security.cert", "TLS certifikat", level,
                                 f"poteče čez {days} dni ({cert})", value=days,
                                 threshold=30, category="security",
                                 remediation={"notify": "Certifikat bo kmalu potekel."}
                                 if level != "ok" else {}))
            break

    if store is not None:
        try:
            db_path = Path(getattr(store, "path", ""))
            if db_path.exists():
                size = db_path.stat().st_size
                level = "warn" if size > 2 * 1024 ** 3 else "ok"
                checks.append(_check("learning.db", "Učna baza", level,
                                     _human(size), value=size,
                                     remediation={"python": "learning_prune"}
                                     if level != "ok" else {},
                                     category="learning"))
        except Exception:
            pass
        try:
            stale = [t for t in store.list_tasks(limit=50, status="running")
                     if time.time() - float(t.get("started") or time.time()) > 3600]
            if stale:
                checks.append(_check("tasks.stale", "Zagozdene naloge", "warn",
                                     f"{len(stale)} nalog teče več kot eno uro",
                                     value=len(stale), category="autonomy"))
        except Exception:
            pass

    uptime = float(metrics.get("uptime") or 0)
    checks.append(_check("system.uptime", "Čas delovanja", "info",
                         _duration(uptime), value=uptime, category="system"))

    score = 100
    for item in checks:
        if item["level"] == "critical":
            score -= 25
        elif item["level"] == "warn":
            score -= 8
    score = max(0, score)
    critical = sum(1 for item in checks if item["level"] == "critical")
    warn = sum(1 for item in checks if item["level"] == "warn")
    overall = "critical" if critical else "warn" if warn else "ok"
    return {"ts": time.time(), "score": score, "level": overall,
            "critical": critical, "warn": warn, "checks": checks,
            "summary": summary({"score": score, "level": overall,
                                "critical": critical, "warn": warn,
                                "checks": checks})}


def _duration(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} dni {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def summary(report: dict) -> str:
    level = report.get("level")
    score = report.get("score", 0)
    if level == "ok":
        return f"Sistem je zdrav, ocena {score} od 100."
    bad = [c for c in report.get("checks") or []
           if c.get("level") in ("warn", "critical")]
    first = bad[0]["message"] if bad else "neznana težava"
    if level == "critical":
        return f"Pozor, šefe: ocena {score} od 100. {first}"
    return f"Ocena {score} od 100. Opazila sem: {first}"


def remediate(report: dict, planner: Any, cfg: dict | None = None,
              *, dry_run: bool = False) -> dict:
    """Run safe fixes. Privileged fixes need `autonomy.auto_remediate`."""
    cfg = cfg or {}
    auto = bool((cfg.get("autonomy") or {}).get("auto_remediate", False))
    actions: list[dict] = []
    for item in report.get("checks") or []:
        if item.get("level") not in ("warn", "critical"):
            continue
        remediation = item.get("remediation") or {}
        if not remediation:
            continue
        if "python" in remediation:
            result = planner._execute_step(
                {"kind": "python", "action": remediation["python"],
                 "args": {}, "expect": {}, "timeout": 120, "retries": 0,
                 "on_fail": "continue", "undo": [], "require_verified": False},
                {"steps": []})
            actions.append({"check": item["key"], "action": remediation["python"],
                            "ok": result.get("ok"), "result": result.get("output")})
        elif "notify" in remediation:
            if dry_run:
                actions.append({"check": item["key"], "action": "notify",
                                "ok": False, "skipped": True,
                                "text": remediation["notify"]})
            else:
                from .planner import make_plan, step_notify
                plan = make_plan([step_notify("Mia", remediation["notify"])],
                                 name=f"zdravje: {item['key']}",
                                 confirmed=True)
                result = planner.execute(plan, name=f"zdravje: {item['key']}",
                                         source="health")
                actions.append({"check": item["key"], "action": "notify",
                                "ok": result.get("ok"),
                                "task_id": result.get("task_id")})
        elif "template" in remediation and auto:
            from .planner import build_template
            plan = build_template(remediation["template"])
            plan["confirmed"] = True
            result = planner.execute(plan, name=f"zdravje: {item['key']}",
                                     source="health")
            actions.append({"check": item["key"], "action": "template:" +
                            remediation["template"], "ok": result.get("ok"),
                            "task_id": result.get("task_id")})
    return {"ok": True, "auto_remediate": auto, "actions": actions,
            "report": report}


def watch(store: Any, report: dict, cooldown: float = 3600) -> list[dict]:
    """Create deduplicated alerts for warn/critical checks."""
    created: list[dict] = []
    if store is None:
        return created
    for item in report.get("checks") or []:
        if item.get("level") not in ("warn", "critical"):
            continue
        key = f"health:{item['key']}:{item['level']}"
        recent = store.list_alerts(limit=100)
        now = time.time()
        duplicate = any(a.get("key") == key and now - float(a.get("ts") or 0) < cooldown
                        for a in recent)
        if duplicate:
            continue
        store.add_alert(item["level"], "health", key, item.get("message") or "",
                        {"check": item.get("key"), "value": item.get("value"),
                         "threshold": item.get("threshold")})
        created.append({"key": key, "level": item["level"]})
    return created
