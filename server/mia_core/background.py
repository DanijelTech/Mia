"""Background inventory helpers (stdlib only).

The HUD »V OZADJU« page lists what Mia started outside the voice turn: desktop
windows from the mia-open registry, holographic panels, stack services and
autonomy jobs. Parsing lives here so it is testable without FastAPI, requests
or a display.
"""

from __future__ import annotations

import json
from pathlib import Path

MEDIA_URL_HINTS = ("youtube", "youtu.be", "soundcloud", "spotify", "vimeo",
                   "twitch", "radio", "music")


def parse_window_registry(text: str) -> list[dict]:
    """Parse ~/.cache/mia-windows (tab-separated: window id, url)."""
    items: list[dict] = []
    for line in (text or "").splitlines():
        wid, sep, url = line.partition("\t")
        wid = wid.strip()
        url = url.strip()
        if sep and wid.isdigit() and url:
            items.append({"wid": wid, "url": url})
    return items


def render_window_registry(items: list[dict]) -> str:
    return "".join(f"{item['wid']}\t{item['url']}\n" for item in items
                   if str(item.get("wid") or "").isdigit() and item.get("url"))


def read_window_registry(path: Path) -> list[dict]:
    try:
        return parse_window_registry(path.read_text(encoding="utf-8"))
    except OSError:
        return []


def is_media_url(url: str) -> bool:
    low = (url or "").lower()
    return any(hint in low for hint in MEDIA_URL_HINTS)


def load_ui_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ui_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8")
