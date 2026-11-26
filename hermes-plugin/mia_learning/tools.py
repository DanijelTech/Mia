"""Handlers: call the Mia voice server's /api/learning/* endpoints.

The plugin runs inside Hermes, so it uses loopback HTTP rather than importing
Mia's server process. The HUD token protects the endpoint; the same token is
already in the Hermes environment for hud_display.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = (os.environ.get("MIA_LEARNING_URL")
        or os.environ.get("JARVIS_LEARNING_URL")
        or "http://127.0.0.1:8765/api/learning")


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
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:300]
        return {"error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # network/loopback failure
        return {"error": f"Mia learning API unreachable: {exc}"}


def memory_brief(args: dict, **kwargs) -> str:
    request = (args.get("request") or "").strip()
    if not request:
        return json.dumps({"error": "request is required"})
    return json.dumps(_request("GET", "/brief?request=" + urllib.parse.quote(request)),
                      ensure_ascii=False)


def memory_search(args: dict, **kwargs) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "query is required"})
    limit = int(args.get("limit") or 20)
    return json.dumps(_request("GET", f"/search?q={urllib.parse.quote(query)}&limit={limit}"),
                      ensure_ascii=False)


def memory_feedback(args: dict, **kwargs) -> str:
    verdict = (args.get("verdict") or "positive").lower()
    payload = {"verdict": verdict, "note": args.get("note") or ""}
    if args.get("episode_id"):
        payload["episode_id"] = int(args["episode_id"])
    return json.dumps(_request("POST", "/feedback", payload), ensure_ascii=False)


def memory_remember(args: dict, **kwargs) -> str:
    payload = {"note": args.get("note") or ""}
    if args.get("episode_id"):
        payload["episode_id"] = int(args["episode_id"])
    return json.dumps(_request("POST", "/remember", payload), ensure_ascii=False)


def memory_fact(args: dict, **kwargs) -> str:
    key = (args.get("key") or "").strip()
    if not key:
        return json.dumps({"error": "key is required"})
    payload = {"key": key, "value": args.get("value") or "",
               "kind": args.get("kind") or "preference"}
    return json.dumps(_request("POST", "/fact", payload), ensure_ascii=False)


def memory_mistake(args: dict, **kwargs) -> str:
    symptom = (args.get("symptom") or "").strip()
    if not symptom:
        return json.dumps({"error": "symptom is required"})
    payload = {"symptom": symptom, "cause": args.get("cause") or "",
               "fix": args.get("fix") or "",
               "severity": args.get("severity") or "medium"}
    return json.dumps(_request("POST", "/mistake", payload), ensure_ascii=False)


def memory_status(args: dict, **kwargs) -> str:
    return json.dumps(_request("GET", "/status"), ensure_ascii=False)


def skill_tree(args: dict, **kwargs) -> str:
    query = (args.get("query") or "").strip().lower()
    data = _request("GET", "/tree")
    if query and "flat" in data:
        matched = [n for n in data.get("flat", [])
                   if query in json.dumps(n, ensure_ascii=False).lower()]
        return json.dumps({"query": query, "matches": matched,
                           "summary": data.get("summary", {})}, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)
