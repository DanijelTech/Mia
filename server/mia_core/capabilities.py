"""Capability inventory: what Mia knows how to do on THIS machine.

The user asked for a rich checklist with confirmed, learned and still-empty
fields. This module owns the catalog and the detection logic; the SQLite table
lives in `db.py`, the HUD page in `server/hud/capabilities.html`, and the CLI
commands in `mia-learn capabilities`.

Statuses
--------
empty        known capability, not checked yet
detected     the required tool/backend is present
learned      Mia actually used it successfully (from the audit log)
confirmed    the user explicitly confirmed it works
failed       the last check/use failed
unsupported  no backend on this machine (with a hint)
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import time
from pathlib import Path
from typing import Any

from .db import Store

STATUSES = ("empty", "detected", "learned", "confirmed", "failed", "unsupported")
CONFIRMED = ("confirmed", "learned")


def _item(cap_id: str, category: str, label: str, how: str,
          keywords: str = "", detect: str = "") -> dict:
    return {"id": cap_id, "category": category, "label": label, "how": how,
            "keywords": keywords or label, "detect": detect}


CATALOG: list[dict] = [
    # ---------------------------------------------------------------- voice
    _item("voice.microphone", "voice", "Mikrofon / zajem zvoka",
          "HUD mikrofon ali `parec`", "mic mikrofon input", "voice"),
    _item("voice.stt", "voice", "Prepis govora (Whisper)",
          "faster-whisper / RealtimeSTT", "stt whisper transkripcija", "voice"),
    _item("voice.tts", "voice", "Govor Mie (TTS)",
          "Piper / Gepard / Maya1 / ElevenLabs", "tts glas govor", "voice"),
    _item("voice.wake", "voice", "Stroga budnica »Mia«",
          "`stt.continuous.strict_wake`", "budnica wake mia", "voice"),
    _item("voice.speaker_gate", "voice", "Prepoznava govorca",
          "`server/speaker_gate.py` + profil", "glas govorec speaker", "voice"),
    _item("voice.distance_calibration", "voice", "Kalibracija po oddaljenosti",
          "HUD → Nastavitve → Kalibriraj glas", "kalibracija oddaljenost", "voice"),
    _item("voice.barge_in", "voice", "Prekinitev med govorjenjem",
          "`stt.continuous.barge_in`", "prekinitev barge", "voice"),
    _item("voice.hud_mic", "voice", "Mikrofon v brskalniku (HTTPS)",
          "HUD + TLS certifikat", "hud brskalnik mik", "voice"),

    # ---------------------------------------------------------------- audio
    _item("audio.volume.up", "audio", "Pojačaj zvok", "`mia-ctl volume up`", "glasneje pojačaj", "volume"),
    _item("audio.volume.down", "audio", "Zmanjšaj zvok", "`mia-ctl volume down`", "tišje zmanjšaj", "volume"),
    _item("audio.volume.set", "audio", "Nastavi glasnost", "`mia-ctl volume set 40`", "glasnost set", "volume"),
    _item("audio.volume.mute", "audio", "Utišaj / odkleni zvok", "`mia-ctl volume mute`", "utišaj mute", "volume"),
    _item("audio.volume.status", "audio", "Preberi glasnost", "`mia-ctl volume status`", "glasnost status", "volume"),
    _item("audio.devices.sinks", "audio", "Izhodne zvočne naprave", "`mia-ctl audio devices`", "zvočniki izhod", "audio_devices"),
    _item("audio.devices.sources", "audio", "Vhodne zvočne naprave", "`mia-ctl audio devices`", "mikrofon vhod", "audio_devices"),

    # --------------------------------------------------------------- display
    _item("display.list", "display", "Seznam zaslonov", "`mia-ctl displays list`", "zaslon monitor display", "displays"),
    _item("display.brightness.up", "display", "Pojačaj svetlost", "`mia-ctl brightness up`", "svetlost brightness", "brightness"),
    _item("display.brightness.down", "display", "Zmanjšaj svetlost", "`mia-ctl brightness down`", "svetlost brightness", "brightness"),
    _item("display.brightness.set", "display", "Nastavi svetlost", "`mia-ctl brightness set 60`", "svetlost brightness", "brightness"),

    # --------------------------------------------------------------- desktop
    _item("desktop.windows.list", "desktop", "Seznam oken", "`mia-ctl windows list`", "okna windows", "windows"),
    _item("desktop.windows.focus", "desktop", "Preklop na okno", "`mia-ctl windows focus <ref>`", "okno focus", "windows"),
    _item("desktop.windows.close", "desktop", "Zapri okno", "`mia-ctl windows close <ref>`", "okno zapri close", "windows"),
    _item("desktop.windows.minimize", "desktop", "Minimiziraj okno", "`mia-ctl windows minimize <ref>`", "okno minimize", "windows"),
    _item("desktop.windows.maximize", "desktop", "Maksimiziraj okno", "`mia-ctl windows maximize <ref>`", "okno maximize", "windows"),
    _item("desktop.windows.move", "desktop", "Premakni/raztegni okno", "`mia-ctl windows move <ref> --x --y --w --h`", "okno move", "windows"),
    _item("desktop.apps.list", "desktop", "Seznam aplikacij", "`mia-ctl apps list`", "aplikacije apps", "apps"),
    _item("desktop.apps.launch", "desktop", "Zaženi aplikacijo", "`mia-ctl apps launch <ime>`", "zaženi aplikacijo launch", "apps"),
    _item("desktop.apps.quit", "desktop", "Zapri aplikacijo", "`mia-ctl apps quit <ime>`", "zapri aplikacijo quit", "apps"),
    _item("desktop.input.type", "desktop", "Tipkanje besedila", "`mia-ctl type \"...\"`", "tipkaj type", "typing"),
    _item("desktop.input.key", "desktop", "Tipke in bližnjice", "`mia-ctl key ctrl+shift+t`", "tipke key", "typing"),
    _item("desktop.input.click", "desktop", "Klik miške", "`mia-ctl click X Y`", "klik click miška", "mouse"),
    _item("desktop.input.move", "desktop", "Premik miške", "`mia-ctl move X Y`", "miška move", "mouse"),
    _item("desktop.input.scroll", "desktop", "Drsenje", "`mia-ctl scroll -3`", "scroll drsenje", "mouse"),
    _item("desktop.screenshot", "desktop", "Posnetek zaslona", "`mia-ctl screenshot`", "posnetek screenshot", "screenshot"),
    _item("desktop.clipboard.get", "desktop", "Preberi odložišče", "`mia-ctl clipboard get`", "odložišče clipboard", "clipboard"),
    _item("desktop.clipboard.set", "desktop", "Nastavi odložišče", "`mia-ctl clipboard set \"...\"`", "odložišče clipboard", "clipboard"),
    _item("desktop.notifications", "desktop", "Namizna obvestila", "`mia-ctl notify <naslov> <besedilo>`", "obvestilo notify", "notifications"),
    _item("desktop.media.play-pause", "desktop", "Predvajaj/pavziraj medije", "`mia-ctl media play-pause`", "mediji media", "media"),
    _item("desktop.media.next", "desktop", "Naslednji medij", "`mia-ctl media next`", "mediji media", "media"),
    _item("desktop.media.previous", "desktop", "Prejšnji medij", "`mia-ctl media previous`", "mediji media", "media"),
    _item("desktop.power.lock", "desktop", "Zakleni zaslon", "`mia-ctl power lock`", "zakleni lock", "power"),
    _item("desktop.power.suspend", "desktop", "Spanje", "`mia-ctl power suspend --yes`", "spanje suspend", "power"),
    _item("desktop.power.reboot", "desktop", "Ponovni zagon", "`mia-ctl power reboot --yes`", "restart reboot", "power"),
    _item("desktop.power.shutdown", "desktop", "Ugasni računalnik", "`mia-ctl power shutdown --yes`", "ugasni shutdown", "power"),

    # ---------------------------------------------------------------- system
    _item("system.resources", "system", "Poraba virov (CPU/RAM/disk/GPU)", "`mia-ctl resources`", "viri cpu ram disk gpu", "resources"),
    _item("system.cpu", "system", "CPU", "`mia-ctl sysinfo`", "cpu procesor", "sysinfo"),
    _item("system.ram", "system", "Pomnilnik", "`mia-ctl sysinfo`", "ram pomnilnik", "sysinfo"),
    _item("system.disk", "system", "Disk", "`mia-ctl sysinfo`", "disk prostor", "sysinfo"),
    _item("system.gpu", "system", "Grafična kartica", "`mia-ctl sysinfo`", "gpu nvidia", "gpu"),
    _item("system.battery", "system", "Baterija", "`mia-ctl sysinfo`", "baterija battery", "battery"),
    _item("system.uptime", "system", "Čas delovanja", "`mia-ctl sysinfo`", "uptime", "sysinfo"),
    _item("system.network", "system", "Omrežje", "`mia-ctl net status`", "omrežje network wifi ip", "net"),
    _item("system.displays", "system", "Zasloni in ločljivosti", "`mia-ctl displays list`", "zaslon display", "displays"),
    _item("system.audio_devices", "system", "Zvočne naprave", "`mia-ctl audio devices`", "zvok audio naprave", "audio_devices"),
    _item("system.process.list", "system", "Seznam procesov", "`mia-ctl process list`", "procesi process", "process"),
    _item("system.process.find", "system", "Iskanje procesa", "`mia-ctl process find <ime>`", "proces process", "process"),
    _item("system.process.kill", "system", "Ustavitev procesa", "`mia-ctl process kill <pid> --yes`", "proces kill", "process"),
    _item("system.service.status", "system", "Stanje storitve", "`mia-ctl service status <unit>`", "storitev service", "service"),
    _item("system.service.start", "system", "Zagon storitve", "`mia-ctl service start <unit>`", "storitev service", "service"),
    _item("system.service.stop", "system", "Ustavitev storitve", "`mia-ctl service stop <unit> --yes`", "storitev service", "service"),
    _item("system.service.restart", "system", "Ponovni zagon storitve", "`mia-ctl service restart <unit> --yes`", "storitev service", "service"),

    # ----------------------------------------------------------------- files
    _item("files.search", "files", "Iskanje datotek", "`mia-ctl files search <q> --root <dir>`", "datoteka iskanje file", "files"),
    _item("files.recent", "files", "Nedavne datoteke", "`mia-ctl files recent`", "nedavne datoteke recent", "files"),
    _item("files.open", "files", "Odpri datoteko", "`mia-ctl files open <pot>`", "odpri datoteko file", "files"),
    _item("files.reveal", "files", "Pokaži datoteko v upravitelju", "`mia-ctl files reveal <pot>`", "pokaži datoteko reveal", "files"),

    # --------------------------------------------------------------- browser
    _item("browser.open", "browser", "Odpri URL v brskalniku", "`mia-ctl open <url>` / `mia-open`", "odpri brskalnik url", "open"),
    _item("browser.google.answer", "browser", "Google: poišči in povej", "server Google intent + `web_search`", "google povej iskanje", "google"),
    _item("browser.google.show", "browser", "Google: prikaži v brskalniku", "`mia-ctl open` Google URL", "google prikaži pokaži", "google"),
    _item("browser.hud_display", "browser", "Prikaz na HUD-u", "Hermes vtičnik `hud_display`", "hud panel prikaz", "hud"),
    _item("browser.hud_dismiss", "browser", "Počisti HUD", "Hermes vtičnik `hud_dismiss`", "hud počisti", "hud"),

    # -------------------------------------------------------------- knowledge
    _item("knowledge.memory", "knowledge", "Trajni spomin (epizode)", "`mia-learn status`", "spomin memory", "knowledge"),
    _item("knowledge.habits", "knowledge", "Navade", "`mia-learn habits`", "navade habits", "knowledge"),
    _item("knowledge.recipes", "knowledge", "Recepti", "`mia-learn recipes`", "recepti recipes", "knowledge"),
    _item("knowledge.mistakes", "knowledge", "Napake / anti-vzorci", "`mia-learn mistakes`", "napake mistakes", "knowledge"),
    _item("knowledge.skills", "knowledge", "Drevo veščin", "`mia-skill validate`", "veščine skills", "knowledge"),
    _item("knowledge.verify", "knowledge", "Preverjanje uspešnosti", "HUD kartica ✓/✗ + `mia-learn verify`", "preveri uspeh verify", "knowledge"),
    _item("knowledge.plugin", "knowledge", "Hermes orodja za spomin", "`hermes plugins enable mia_learning`", "plugin memory orodja", "plugin"),

    # --------------------------------------------------------------- security
    _item("security.policy", "security", "Politika nadzora", "`mia-ctl policy show`", "politika policy", "policy"),
    _item("security.audit", "security", "Revizija dejanj", "`mia-ctl audit tail`", "revizija audit", "audit"),
    _item("security.redaction", "security", "Prekrivanje skrivnosti", "`mia_core/privacy.py`", "skrivnosti redaction", "knowledge"),
]


def _has(name: str) -> bool:
    return bool(shutil.which(name))


def _desktop() -> str:
    if platform.system() == "Darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    if os.environ.get("SWAYSOCK") and _has("swaymsg"):
        return "sway"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and _has("hyprctl"):
        return "hyprland"
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "headless"


def _first_tool(*names: str) -> str:
    for name in names:
        if _has(name):
            return name
    return ""


def _detect(item: dict, extra: dict) -> tuple[str, str]:
    cap_id = item["id"]
    if cap_id in extra:
        value = extra[cap_id]
        if isinstance(value, tuple):
            return value
        if isinstance(value, dict):
            return value.get("status", "detected"), value.get("evidence", "")
        return str(value), ""
    detect = item.get("detect") or ""
    desktop = _desktop()
    if detect == "voice":
        return "detected", "voice server running"
    if detect == "volume":
        tool = _first_tool("mia-volume", "wpctl", "pactl")
        return ("detected", tool) if tool else ("unsupported", "install wireplumber/pulseaudio")
    if detect == "audio_devices":
        tool = _first_tool("pactl", "wpctl")
        return ("detected", tool) if tool else ("unsupported", "install pactl or wpctl")
    if detect == "displays":
        tool = _first_tool("xrandr", "wlr-randr", "swaymsg", "hyprctl", "system_profiler")
        return ("detected", tool) if tool else ("unsupported", "install xrandr/wlr-randr")
    if detect == "brightness":
        return ("detected", "brightnessctl") if _has("brightnessctl") else (
            "unsupported", "install brightnessctl")
    if detect == "windows":
        tool = _first_tool("wmctrl", "swaymsg", "hyprctl", "osascript", "powershell")
        return ("detected", tool) if tool else ("unsupported", "install wmctrl/xdotool")
    if detect == "apps":
        if desktop == "macos":
            return "detected", "open -a"
        if desktop == "windows":
            return "detected", "PowerShell"
        tool = _first_tool("gtk-launch", "gio", "xdg-open")
        return ("detected", tool) if tool else ("unsupported", "install gtk-launch/gio")
    if detect == "typing":
        tool = _first_tool("xdotool", "wtype", "ydotool", "osascript", "powershell")
        return ("detected", tool) if tool else ("unsupported", "install xdotool/wtype")
    if detect == "mouse":
        tool = _first_tool("xdotool", "ydotool", "cliclick", "powershell")
        return ("detected", tool) if tool else ("unsupported", "install xdotool/ydotool")
    if detect == "screenshot":
        tool = _first_tool("grim", "gnome-screenshot", "spectacle", "scrot",
                           "import", "screencapture", "powershell")
        return ("detected", tool) if tool else ("unsupported", "install grim/scrot")
    if detect == "clipboard":
        tool = _first_tool("wl-copy", "xclip", "xsel", "pbcopy", "powershell")
        return ("detected", tool) if tool else ("unsupported", "install wl-clipboard/xclip")
    if detect == "notifications":
        tool = _first_tool("notify-send", "osascript")
        return ("detected", tool) if tool else ("unsupported", "install libnotify-bin")
    if detect == "media":
        tool = _first_tool("playerctl", "osascript")
        return ("detected", tool) if tool else ("unsupported", "install playerctl")
    if detect == "power":
        tool = _first_tool("systemctl", "loginctl", "pmset", "shutdown")
        return ("detected", tool) if tool else ("unsupported", "no power backend")
    if detect == "resources" or detect == "sysinfo":
        return "detected", platform.system()
    if detect == "gpu":
        return ("detected", "nvidia-smi") if _has("nvidia-smi") else (
            "unsupported", "nvidia-smi not found (CPU-only?)")
    if detect == "battery":
        base = Path("/sys/class/power_supply")
        found = base.is_dir() and any(p.name.startswith("BAT") for p in base.iterdir())
        return ("detected", "power_supply") if found else (
            "unsupported", "no battery device")
    if detect == "net":
        tool = _first_tool("ip", "nmcli", "route", "ipconfig")
        return ("detected", tool) if tool else ("unsupported", "no network tool")
    if detect == "process":
        tool = _first_tool("ps", "tasklist", "psutil")
        return ("detected", tool or "python psutil") if (tool or _has("ps")) else (
            "unsupported", "no process backend")
    if detect == "service":
        tool = _first_tool("systemctl", "launchctl", "powershell")
        return ("detected", tool) if tool else ("unsupported", "no service manager")
    if detect == "files":
        return "detected", "filesystem"
    if detect == "open":
        tool = _first_tool("mia-open", "xdg-open", "open")
        return ("detected", tool) if tool else ("unsupported", "install xdg-utils")
    if detect == "google":
        return "detected", "server intent + web_search"
    if detect == "hud":
        for base in (Path.home() / ".hermes" / "plugins", Path("hermes-plugin")):
            if (base / "hud_display").is_dir():
                return "detected", str(base / "hud_display")
        return "unsupported", "install hermes-plugin/hud_display"
    if detect == "plugin":
        for base in (Path.home() / ".hermes" / "plugins", Path("hermes-plugin")):
            if (base / "mia_learning").is_dir():
                return "detected", str(base / "mia_learning")
        return "unsupported", "install hermes-plugin/mia_learning"
    if detect == "policy":
        path = Path(os.environ.get("MIA_CONTROL_POLICY",
                                   Path.home() / ".config" / "mia" / "control.json"))
        return ("detected", str(path)) if path.exists() else (
            "empty", "run install.sh or create ~/.config/mia/control.json")
    if detect == "audit":
        path = Path(os.environ.get("MIA_CONTROL_AUDIT",
                                   Path.home() / ".local" / "state" / "mia" /
                                   "control-audit.jsonl"))
        return ("detected", str(path)) if path.exists() else (
            "empty", "no control action yet")
    if detect == "knowledge":
        return "detected", "mia_core"
    return "empty", ""


def ensure_catalog(store: Store) -> int:
    now = time.time()
    with store._lock:  # same package, one short transaction
        for item in CATALOG:
            store._conn.execute(
                """INSERT INTO capabilities(id, category, label, how, keywords,
                   status, evidence, notes, last_checked, last_confirmed, source)
                   VALUES(?,?,?,?,?,'empty','','',?,NULL,'catalog')
                   ON CONFLICT(id) DO UPDATE SET category=excluded.category,
                     label=excluded.label, how=excluded.how, keywords=excluded.keywords""",
                (item["id"], item["category"], item["label"], item["how"],
                 item["keywords"], now),
            )
        store._conn.commit()
    return len(CATALOG)


def refresh(store: Store, cfg: dict | None = None,
            extra: dict | None = None) -> dict:
    ensure_catalog(store)
    extra = extra or {}
    rows = store.list_capabilities(limit=500)
    catalog = {item["id"]: item for item in CATALOG}
    changed = 0
    for row in rows:
        if row["status"] in CONFIRMED:
            continue  # user confirmation / real successful use is stronger
        item = {**catalog.get(row["id"], {}), **row}
        status, evidence = _detect(item, extra)
        if status != row["status"] or evidence != (row.get("evidence") or ""):
            store.set_capability(row["id"], status, evidence=evidence,
                                 source="auto")
            changed += 1
    return {"checked": len(rows), "changed": changed,
            "summary": summary(store)}


def confirm(store: Store, cap_id: str, status: str = "confirmed",
            notes: str = "", evidence: str = "") -> bool:
    if status not in STATUSES:
        status = "confirmed"
    return store.set_capability(cap_id, status, evidence=evidence,
                                notes=notes, source="user")


def mark_learned(store: Store, action: str, ok: bool = True) -> None:
    """Map an executed action to a capability and mark it learned."""
    mapping = {
        "volume": "audio.volume",
        "brightness": "display.brightness",
        "windows": "desktop.windows",
        "apps": "desktop.apps",
        "type": "desktop.input.type",
        "key": "desktop.input.key",
        "click": "desktop.input.click",
        "move": "desktop.input.move",
        "scroll": "desktop.input.scroll",
        "screenshot": "desktop.screenshot",
        "clipboard": "desktop.clipboard",
        "notify": "desktop.notifications",
        "media": "desktop.media",
        "power": "desktop.power",
        "process": "system.process",
        "service": "system.service",
        "files": "files",
        "displays": "display.list",
        "resources": "system.resources",
        "audio devices": "system.audio_devices",
        "net": "system.network",
        "open": "browser.open",
    }
    base = mapping.get(action) or mapping.get(action.split(" ", 1)[0])
    if not base:
        return
    candidates = [base]
    if base in ("audio.volume", "display.brightness", "desktop.windows",
                "desktop.apps", "desktop.clipboard", "desktop.media",
                "desktop.power", "system.process", "system.service", "files"):
        suffix = action.split(" ", 1)[1] if " " in action else ""
        candidates.insert(0, f"{base}.{suffix}")
    for cap_id in candidates:
        row = store.get_capability(cap_id)
        if row and row["status"] != "confirmed":
            store.set_capability(cap_id, "learned" if ok else "failed",
                                 evidence=f"used: {action}", source="audit")
            return


def lines(store: Store, query: str = "", limit: int = 8) -> list[str]:
    rows = [r for r in store.list_capabilities(limit=500)
            if r["status"] in CONFIRMED]
    if query:
        from .recipes import similarity
        rows.sort(key=lambda r: similarity(
            query, f"{r['label']} {r['how']} {r.get('keywords') or ''}"),
            reverse=True)
    return [f"{r['label']}: {r['how']} ({r['status']})" for r in rows[:limit]]


def summary(store: Store) -> dict:
    rows = store.list_capabilities(limit=500)
    by_status: dict[str, int] = {s: 0 for s in STATUSES}
    by_category: dict[str, dict] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        cat = by_category.setdefault(row["category"], {"total": 0, "confirmed": 0,
                                                       "learned": 0, "empty": 0,
                                                       "unsupported": 0})
        cat["total"] += 1
        if row["status"] in ("confirmed", "learned"):
            cat[row["status"]] += 1
        elif row["status"] in ("empty", "unsupported"):
            cat[row["status"]] += 1
    total = len(rows)
    confirmed = by_status.get("confirmed", 0) + by_status.get("learned", 0)
    return {"total": total, "confirmed": confirmed,
            "percent": round(confirmed / total * 100) if total else 0,
            "by_status": by_status, "by_category": by_category}
