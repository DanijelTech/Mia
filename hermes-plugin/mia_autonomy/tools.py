"""Handlers: call the Mia voice server's /api/autonomy/* endpoints.

The plugin runs inside Hermes, so it uses loopback HTTP rather than importing
Mia's server process. The HUD token protects the endpoint; the same token is
already in the Hermes environment for hud_display and mia_learning.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = (os.environ.get("MIA_AUTONOMY_URL")
        or os.environ.get("JARVIS_AUTONOMY_URL")
        or "http://127.0.0.1:8765/api/autonomy")


def _token() -> str:
    return (os.environ.get("MIA_HUD_TOKEN")
            or os.environ.get("JARVIS_HUD_TOKEN")
            or "")


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE.rstrip("/") + path, data=data, method=method,
        headers={"Content-Type": "application/json", "X-Mia-Token": _token()},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:500]
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                parsed.setdefault("http_status", exc.code)
                return parsed
        except ValueError:
            pass
        return {"error": f"HTTP {exc.code}: {detail}", "http_status": exc.code}
    except Exception as exc:  # network/loopback failure
        return {"error": f"Mia autonomy API unreachable: {exc}"}


def system_status(args: dict, **kwargs) -> str:
    return json.dumps(_request("GET", "/status"), ensure_ascii=False)


def system_profile(args: dict, **kwargs) -> str:
    refresh = "1" if args.get("refresh") else "0"
    return json.dumps(_request("GET", f"/profile?refresh={refresh}"),
                      ensure_ascii=False)


def system_health(args: dict, **kwargs) -> str:
    force = "1" if args.get("force", True) else "0"
    return json.dumps(_request("GET", f"/health?force={force}"),
                      ensure_ascii=False)


def system_adapt(args: dict, **kwargs) -> str:
    return json.dumps(_request("POST", "/adapt",
                               {"apply": bool(args.get("apply", False))}),
                      ensure_ascii=False)


def system_plans(args: dict, **kwargs) -> str:
    return json.dumps(_request("GET", "/plans"), ensure_ascii=False)


def system_run_plan(args: dict, **kwargs) -> str:
    template = (args.get("template") or "").strip()
    plan = args.get("plan")
    if not template and not plan:
        return json.dumps({"error": "template or plan is required"})
    payload: dict = {"confirm": bool(args.get("confirm", False))}
    if template:
        payload["template"] = template
    if plan:
        payload["plan"] = plan
    return json.dumps(_request("POST", "/run", payload), ensure_ascii=False)


def system_command(args: dict, **kwargs) -> str:
    text = (args.get("input") or args.get("text") or "").strip()
    if not text:
        return json.dumps({"error": "input is required"})
    return json.dumps(_request("POST", "/text",
                               {"input": text,
                                "conversation": args.get("conversation") or "mia-main"}),
                      ensure_ascii=False)


def system_jobs(args: dict, **kwargs) -> str:
    kind = (args.get("kind") or "").strip()
    path = "/jobs" + (f"?kind={kind}" if kind else "")
    return json.dumps(_request("GET", path), ensure_ascii=False)


def system_job_add(args: dict, **kwargs) -> str:
    name = (args.get("name") or "").strip()
    if not name:
        return json.dumps({"error": "name is required"})
    trigger = args.get("trigger") or {"kind": "every", "seconds": 3600}
    if isinstance(trigger, str):
        try:
            trigger = json.loads(trigger)
        except ValueError:
            return json.dumps({"error": "trigger must be a JSON object"})
    payload = {"name": name, "trigger": trigger,
               "kind": args.get("kind") or "job",
               "enabled": bool(args.get("enabled", True)),
               "max_runs": int(args.get("max_runs") or 0)}
    if args.get("conditions"):
        conditions = args["conditions"]
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except ValueError:
                return json.dumps({"error": "conditions must be JSON"})
        payload["conditions"] = conditions
    if args.get("template"):
        payload["template"] = args["template"]
    elif args.get("plan"):
        payload["plan"] = args["plan"]
    else:
        payload["notify"] = args.get("notify") or "Mia"
        payload["text"] = args.get("text") or args.get("body") or name
    return json.dumps(_request("POST", "/jobs", payload), ensure_ascii=False)


def system_job_remove(args: dict, **kwargs) -> str:
    try:
        job_id = int(args.get("job_id") or 0)
    except (TypeError, ValueError):
        job_id = 0
    if not job_id:
        return json.dumps({"error": "job_id is required"})
    return json.dumps(_request("DELETE", f"/jobs/{job_id}"), ensure_ascii=False)


def system_tasks(args: dict, **kwargs) -> str:
    limit = max(1, min(100, int(args.get("limit") or 20)))
    return json.dumps(_request("GET", f"/tasks?limit={limit}"), ensure_ascii=False)


def system_task_resume(args: dict, **kwargs) -> str:
    try:
        task_id = int(args.get("task_id") or 0)
    except (TypeError, ValueError):
        task_id = 0
    if not task_id:
        return json.dumps({"error": "task_id is required"})
    return json.dumps(_request("POST", f"/tasks/{task_id}/resume", {}),
                      ensure_ascii=False)


def system_task_cancel(args: dict, **kwargs) -> str:
    try:
        task_id = int(args.get("task_id") or 0)
    except (TypeError, ValueError):
        task_id = 0
    if not task_id:
        return json.dumps({"error": "task_id is required"})
    return json.dumps(_request("POST", f"/tasks/{task_id}/cancel", {}),
                      ensure_ascii=False)


def system_alerts(args: dict, **kwargs) -> str:
    limit = max(1, min(100, int(args.get("limit") or 20)))
    return json.dumps(_request("GET", f"/alerts?limit={limit}"),
                      ensure_ascii=False)


def system_alert_ack(args: dict, **kwargs) -> str:
    try:
        alert_id = int(args.get("alert_id") or 0)
    except (TypeError, ValueError):
        alert_id = 0
    if not alert_id:
        return json.dumps({"error": "alert_id is required"})
    return json.dumps(_request("POST", f"/alerts/{alert_id}/ack", {}),
                      ensure_ascii=False)
