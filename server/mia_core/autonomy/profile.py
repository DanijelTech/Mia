"""Adaptive machine profile: what this computer is and what it can do.

The autonomy layer must behave differently on a GNOME/X11 laptop, a headless
Ubuntu server, a Sway desktop and a container. This module discovers the machine
once, exposes the result as plain data, and turns missing tools into an explicit
adaptation plan (which package to install for which capability).

It is deliberately stdlib-only: it runs inside the voice server, inside the
`mia-auto` CLI and in tests on a bare container.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

# Capability -> ordered backend chain. The first present tool wins.
BACKEND_CHAINS: dict[str, list[str]] = {
    "volume": ["wpctl", "pactl", "amixer"],
    "brightness": ["brightnessctl", "light", "xrandr"],
    "windows.x11": ["wmctrl", "xdotool"],
    "windows.sway": ["swaymsg"],
    "windows.hyprland": ["hyprctl"],
    "typing": ["xdotool", "wtype", "ydotool"],
    "mouse": ["xdotool", "ydotool"],
    "screenshot": ["grim", "gnome-screenshot", "spectacle", "scrot", "import"],
    "clipboard": ["wl-copy", "xclip", "xsel"],
    "notifications": ["notify-send"],
    "media": ["playerctl"],
    "open": ["xdg-open", "gio"],
    "displays": ["xrandr", "wlr-randr", "swaymsg", "hyprctl"],
    "network": ["nmcli", "ip", "iw"],
    "firewall": ["ufw", "firewall-cmd", "nft"],
    "archive": ["tar", "zip", "unzip"],
    "trash": ["trash", "gio"],
    "monitoring": ["sensors", "nvidia-smi"],
    "process": ["ps"],
    "service": ["systemctl"],
    "files": ["find", "du", "df"],
    "privilege": ["sudo", "doas"],
}

# Tool -> package name per package manager. Unknown pairs are omitted.
PACKAGE_MAP: dict[str, dict[str, str]] = {
    "wpctl": {"apt": "wireplumber", "dnf": "wireplumber", "pacman": "wireplumber",
              "zypper": "wireplumber", "apk": "wireplumber"},
    "pactl": {"apt": "pulseaudio-utils", "dnf": "pulseaudio-utils",
              "pacman": "libpulse", "zypper": "pulseaudio-utils"},
    "brightnessctl": {"apt": "brightnessctl", "dnf": "brightnessctl",
                      "pacman": "brightnessctl", "zypper": "brightnessctl",
                      "apk": "brightnessctl"},
    "wmctrl": {"apt": "wmctrl", "dnf": "wmctrl", "pacman": "wmctrl",
               "zypper": "wmctrl", "apk": "wmctrl"},
    "xdotool": {"apt": "xdotool", "dnf": "xdotool", "pacman": "xdotool",
                "zypper": "xdotool", "apk": "xdotool"},
    "wtype": {"apt": "wtype", "dnf": "wtype", "pacman": "wtype",
              "zypper": "wtype", "apk": "wtype"},
    "ydotool": {"apt": "ydotool", "dnf": "ydotool", "pacman": "ydotool"},
    "grim": {"apt": "grim", "dnf": "grim", "pacman": "grim", "zypper": "grim",
             "apk": "grim"},
    "gnome-screenshot": {"apt": "gnome-screenshot", "dnf": "gnome-screenshot",
                         "pacman": "gnome-screenshot"},
    "spectacle": {"apt": "spectacle", "dnf": "spectacle", "pacman": "spectacle"},
    "scrot": {"apt": "scrot", "dnf": "scrot", "pacman": "scrot"},
    "wl-copy": {"apt": "wl-clipboard", "dnf": "wl-clipboard",
                "pacman": "wl-clipboard", "zypper": "wl-clipboard",
                "apk": "wl-clipboard"},
    "xclip": {"apt": "xclip", "dnf": "xclip", "pacman": "xclip",
              "zypper": "xclip", "apk": "xclip"},
    "xsel": {"apt": "xsel", "dnf": "xsel", "pacman": "xsel"},
    "notify-send": {"apt": "libnotify-bin", "dnf": "libnotify",
                    "pacman": "libnotify", "zypper": "libnotify-tools",
                    "apk": "libnotify"},
    "playerctl": {"apt": "playerctl", "dnf": "playerctl", "pacman": "playerctl",
                  "zypper": "playerctl", "apk": "playerctl"},
    "xdg-open": {"apt": "xdg-utils", "dnf": "xdg-utils", "pacman": "xdg-utils",
                 "zypper": "xdg-utils", "apk": "xdg-utils"},
    "xrandr": {"apt": "x11-xserver-utils", "dnf": "xrandr", "pacman": "xorg-xrandr",
               "zypper": "xrandr"},
    "wlr-randr": {"apt": "wlr-randr", "dnf": "wlr-randr", "pacman": "wlr-randr"},
    "nmcli": {"apt": "network-manager", "dnf": "NetworkManager",
              "pacman": "networkmanager", "zypper": "NetworkManager",
              "apk": "networkmanager"},
    "ufw": {"apt": "ufw", "dnf": "ufw", "pacman": "ufw", "zypper": "ufw"},
    "tar": {"apt": "tar", "dnf": "tar", "pacman": "tar", "zypper": "tar",
            "apk": "tar"},
    "zip": {"apt": "zip", "dnf": "zip", "pacman": "zip", "zypper": "zip",
            "apk": "zip"},
    "unzip": {"apt": "unzip", "dnf": "unzip", "pacman": "unzip",
              "zypper": "unzip", "apk": "unzip"},
    "trash": {"apt": "trash-cli", "dnf": "trash-cli", "pacman": "trash-cli"},
    "sensors": {"apt": "lm-sensors", "dnf": "lm_sensors", "pacman": "lm_sensors",
                "zypper": "sensors", "apk": "lm-sensors"},
    "find": {"apt": "findutils", "dnf": "findutils", "pacman": "findutils",
             "zypper": "findutils", "apk": "findutils"},
    "du": {"apt": "coreutils", "dnf": "coreutils", "pacman": "coreutils",
           "zypper": "coreutils", "apk": "coreutils"},
    "sudo": {"apt": "sudo", "dnf": "sudo", "pacman": "sudo", "zypper": "sudo",
             "apk": "sudo"},
    "ffmpeg": {"apt": "ffmpeg", "dnf": "ffmpeg", "pacman": "ffmpeg",
               "zypper": "ffmpeg", "apk": "ffmpeg"},
    "rsync": {"apt": "rsync", "dnf": "rsync", "pacman": "rsync",
              "zypper": "rsync", "apk": "rsync"},
    "jq": {"apt": "jq", "dnf": "jq", "pacman": "jq", "zypper": "jq", "apk": "jq"},
    "rg": {"apt": "ripgrep", "dnf": "ripgrep", "pacman": "ripgrep",
           "zypper": "ripgrep", "apk": "ripgrep"},
}

# Readiness groups shown in the HUD and used to adapt capabilities.
READINESS_GROUPS: list[dict] = [
    {"id": "audio.volume", "label": "Glasnost", "category": "audio",
     "tools": ["wpctl", "pactl"], "hint": "Namesti wireplumber ali pulseaudio-utils."},
    {"id": "display.brightness", "label": "Svetlost zaslona", "category": "display",
     "tools": ["brightnessctl"], "hint": "Namesti brightnessctl."},
    {"id": "desktop.windows", "label": "Upravljanje oken", "category": "desktop",
     "tools": ["wmctrl", "swaymsg", "hyprctl"], "hint": "Namesti wmctrl (X11) ali uporabi sway/hyprland."},
    {"id": "desktop.input.type", "label": "Tipkanje in bližnjice", "category": "desktop",
     "tools": ["xdotool", "wtype", "ydotool"], "hint": "Namesti xdotool (X11) ali wtype/ydotool (Wayland)."},
    {"id": "desktop.input.click", "label": "Miška", "category": "desktop",
     "tools": ["xdotool", "ydotool"], "hint": "Namesti xdotool ali ydotool."},
    {"id": "desktop.screenshot", "label": "Posnetek zaslona", "category": "desktop",
     "tools": ["grim", "gnome-screenshot", "spectacle", "scrot", "import"],
     "hint": "Namesti grim (Wayland) ali scrot/gnome-screenshot."},
    {"id": "desktop.clipboard", "label": "Odložišče", "category": "desktop",
     "tools": ["wl-copy", "xclip", "xsel"], "hint": "Namesti wl-clipboard ali xclip."},
    {"id": "desktop.notifications", "label": "Obvestila", "category": "desktop",
     "tools": ["notify-send"], "hint": "Namesti libnotify-bin."},
    {"id": "desktop.media", "label": "Predvajalnik", "category": "desktop",
     "tools": ["playerctl"], "hint": "Namesti playerctl."},
    {"id": "browser.open", "label": "Odpiranje povezav", "category": "browser",
     "tools": ["xdg-open", "gio"], "hint": "Namesti xdg-utils."},
    {"id": "display.list", "label": "Zasloni", "category": "display",
     "tools": ["xrandr", "wlr-randr", "swaymsg", "hyprctl"], "hint": "Namesti xrandr ali wlr-randr."},
    {"id": "system.network", "label": "Omrežje in Wi-Fi", "category": "system",
     "tools": ["nmcli", "ip"], "hint": "Namesti network-manager ali iproute2."},
    {"id": "system.firewall", "label": "Požarni zid", "category": "security",
     "tools": ["ufw", "firewall-cmd", "nft"], "hint": "Namesti ufw ali firewalld."},
    {"id": "system.service", "label": "Storitve", "category": "system",
     "tools": ["systemctl"], "hint": "Sistem brez systemd: storitve niso na voljo."},
    {"id": "files.archive", "label": "Arhivi", "category": "files",
     "tools": ["tar", "zip", "unzip"], "hint": "Namesti tar, zip in unzip."},
    {"id": "files.trash", "label": "Smeti (varno brisanje)", "category": "files",
     "tools": ["trash", "gio"], "hint": "Namesti trash-cli (Mia uporabi XDG koš tudi brez njega)."},
    {"id": "system.monitoring", "label": "Senzorji in GPU", "category": "system",
     "tools": ["sensors", "nvidia-smi"], "hint": "Namesti lm-sensors; nvidia-smi pride z gonilnikom."},
    {"id": "system.privilege", "label": "Skrbniške pravice", "category": "security",
     "tools": ["sudo", "doas"], "hint": "Namesti sudo ali doas."},
    {"id": "files.search", "label": "Iskanje datotek", "category": "files",
     "tools": ["find"], "hint": "Namesti findutils."},
]

PACKAGE_MANAGERS: dict[str, dict[str, Any]] = {
    "apt": {"bin": "apt-get", "query": "dpkg-query", "search": "apt-cache",
            "install": ["apt-get", "install", "-y", "--no-install-recommends"],
            "remove": ["apt-get", "remove", "-y"],
            "update": ["apt-get", "update"],
            "upgrade": ["apt-get", "upgrade", "-y"],
            "list_upgradable": ["apt", "list", "--upgradable"],
            "clean": ["apt-get", "autoremove", "-y"]},
    "dnf": {"bin": "dnf", "search": "dnf",
            "install": ["dnf", "install", "-y"], "remove": ["dnf", "remove", "-y"],
            "update": ["dnf", "makecache"], "upgrade": ["dnf", "upgrade", "-y"],
            "list_upgradable": ["dnf", "list", "--upgrades"],
            "clean": ["dnf", "autoremove", "-y"]},
    "pacman": {"bin": "pacman", "search": "pacman",
               "install": ["pacman", "-S", "--noconfirm"],
               "remove": ["pacman", "-R", "--noconfirm"],
               "update": ["pacman", "-Sy"], "upgrade": ["pacman", "-Su", "--noconfirm"],
               "list_upgradable": ["pacman", "-Qu"],
               "clean": ["pacman", "-Rns", "--noconfirm"]},
    "zypper": {"bin": "zypper", "search": "zypper",
               "install": ["zypper", "--non-interactive", "install"],
               "remove": ["zypper", "--non-interactive", "remove"],
               "update": ["zypper", "refresh"], "upgrade": ["zypper", "--non-interactive", "update"],
               "list_upgradable": ["zypper", "list-updates"],
               "clean": ["zypper", "--non-interactive", "removeorphans"]},
    "apk": {"bin": "apk", "search": "apk",
            "install": ["apk", "add"], "remove": ["apk", "del"],
            "update": ["apk", "update"], "upgrade": ["apk", "upgrade"],
            "list_upgradable": ["apk", "version", "-l", "<"],
            "clean": ["apk", "del"]},
    "brew": {"bin": "brew", "search": "brew",
             "install": ["brew", "install"], "remove": ["brew", "uninstall"],
             "update": ["brew", "update"], "upgrade": ["brew", "upgrade"],
             "list_upgradable": ["brew", "outdated"],
             "clean": ["brew", "cleanup"]},
}


def _run(argv: list[str], timeout: float = 2.5,
         env: dict | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, env=env)
        return proc.returncode, (proc.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def _read(path: str | Path, limit: int = 65536) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _parse_os_release() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _read("/etc/os-release").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _which(name: str) -> str | None:
    return shutil.which(name)


def _first(tools: list[str]) -> str:
    for tool in tools:
        if _which(tool):
            return tool
    return ""


def _cpu_model() -> str:
    text = _read("/proc/cpuinfo", 200000)
    for line in text.splitlines():
        if line.lower().startswith(("model name", "hardware", "processor")):
            _, _, value = line.partition(":")
            value = value.strip()
            if value and not value.isdigit():
                return value[:120]
    return platform.processor() or platform.machine()


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.strip().split()
        if parts and parts[0].isdigit():
            out[key.strip()] = int(parts[0]) * 1024
    return out


def _disk(path: str | Path) -> dict:
    try:
        usage = shutil.disk_usage(str(path))
    except OSError:
        return {"total": 0, "used": 0, "free": 0, "percent": 0.0}
    total = usage.total or 1
    return {"total": usage.total, "used": usage.used, "free": usage.free,
            "percent": round(usage.used / total * 100, 1)}


def _battery() -> dict:
    base = Path("/sys/class/power_supply")
    if not base.is_dir():
        return {"present": False}
    for entry in sorted(base.iterdir()):
        if not entry.name.startswith("BAT"):
            continue
        percent = _read(entry / "capacity").strip()
        status = _read(entry / "status").strip()
        try:
            value = int(percent)
        except ValueError:
            value = None
        return {"present": True, "percent": value, "status": status.lower(),
                "on_battery": status.lower() == "discharging"}
    return {"present": False}


def _temperatures() -> list[dict]:
    out: list[dict] = []
    base = Path("/sys/class/thermal")
    if base.is_dir():
        for zone in sorted(base.glob("thermal_zone*")):
            raw = _read(zone / "temp").strip()
            try:
                celsius = float(raw) / (1000.0 if float(raw) > 200 else 1.0)
            except ValueError:
                continue
            out.append({"zone": zone.name, "celsius": round(celsius, 1)})
    return out


def _network() -> dict:
    interfaces: list[dict] = []
    base = Path("/sys/class/net")
    if base.is_dir():
        for net in sorted(base.iterdir()):
            if net.name == "lo":
                continue
            state = _read(net / "operstate").strip()
            mac = _read(net / "address").strip()
            wireless = (net / "wireless").exists() or (net / "phy80211").exists()
            interfaces.append({"name": net.name, "state": state,
                               "wireless": wireless, "mac": mac})
    default_gateway = ""
    for line in _read("/proc/net/route").splitlines()[1:]:
        parts = line.split()
        if len(parts) > 2 and parts[1] == "00000000":
            try:
                default_gateway = socket.inet_ntoa(
                    bytes.fromhex(parts[2])[::-1])
            except (ValueError, OSError):
                pass
            break
    addresses: list[str] = []
    if _which("ip"):
        _, text = _run(["ip", "-o", "-4", "addr", "show"], 2.0)
        for line in text.splitlines():
            match = re.search(r"\s(\d+\.\d+\.\d+\.\d+/\d+)\s", line)
            if match and not match.group(1).startswith("127."):
                addresses.append(match.group(1))
    if not addresses:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.2)
                sock.connect(("8.8.8.8", 80))
                addresses.append(sock.getsockname()[0])
        except OSError:
            pass
    wifi = {"available": any(i["wireless"] for i in interfaces),
            "connected": any(i["wireless"] and i["state"] == "up"
                             for i in interfaces),
            "ssid": ""}
    if _which("nmcli"):
        rc, text = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], 2.5)
        if rc == 0:
            for line in text.splitlines():
                if line.startswith("yes:"):
                    wifi["ssid"] = line.split(":", 1)[1]
                    break
    return {"interfaces": interfaces, "default_gateway": default_gateway,
            "addresses": addresses, "wifi": wifi}


def _gpu() -> dict:
    if _which("nvidia-smi"):
        rc, text = _run(["nvidia-smi", "--query-gpu=name,memory.total",
                         "--format=csv,noheader"], 3.0)
        if rc == 0 and text:
            name, _, memory = text.splitlines()[0].partition(",")
            return {"present": True, "vendor": "nvidia",
                    "name": name.strip(), "memory": memory.strip()}
    if Path("/dev/dri").is_dir():
        return {"present": True, "vendor": "generic", "name": "DRM device"}
    return {"present": False}


def _desktop() -> dict:
    env = os.environ
    if platform.system() == "Darwin":
        return {"kind": "macos", "display": "aqua", "session": "aqua"}
    if os.name == "nt":
        return {"kind": "windows", "display": "win32", "session": "win32"}
    kind = "headless"
    if env.get("SWAYSOCK") and _which("swaymsg"):
        kind = "sway"
    elif env.get("HYPRLAND_INSTANCE_SIGNATURE") and _which("hyprctl"):
        kind = "hyprland"
    elif env.get("WAYLAND_DISPLAY"):
        kind = "wayland"
    elif env.get("DISPLAY"):
        kind = "x11"
    session = env.get("XDG_SESSION_TYPE") or (
        "wayland" if kind in ("sway", "hyprland", "wayland") else
        "x11" if kind == "x11" else "tty")
    return {"kind": kind, "display": env.get("DISPLAY") or env.get("WAYLAND_DISPLAY") or "",
            "session": session,
            "desktop": env.get("XDG_CURRENT_DESKTOP") or env.get("DESKTOP_SESSION") or "",
            "has_display": kind != "headless"}


def _init_system() -> str:
    if Path("/run/systemd/system").is_dir():
        return "systemd"
    if _which("rc-status") and Path("/run/openrc").exists():
        return "openrc"
    if _which("launchctl"):
        return "launchd"
    if Path("/sbin/init").exists():
        return "sysvinit"
    return "unknown"


def _package_manager() -> dict:
    for name, meta in PACKAGE_MANAGERS.items():
        if _which(meta["bin"]):
            return {"name": name, **meta}
    return {}


def _privilege(manager: dict) -> dict:
    uid = os.getuid() if hasattr(os, "getuid") else -1
    sudo = _which("sudo")
    doas = _which("doas")
    non_interactive = False
    if uid != 0 and sudo:
        rc, _ = _run(["sudo", "-n", "true"], 1.5)
        non_interactive = rc == 0
    if uid != 0 and doas:
        rc, _ = _run(["doas", "-n", "true"], 1.5)
        non_interactive = non_interactive or rc == 0
    prefix: list[str] = []
    if uid != 0:
        if non_interactive:
            prefix = ["sudo", "-n"] if sudo else ["doas", "-n"]
        else:
            prefix = []
    brew = (manager or {}).get("name") == "brew"
    return {"uid": uid, "is_root": uid == 0, "sudo": bool(sudo),
            "doas": bool(doas), "non_interactive": non_interactive,
            "can_elevate": brew or uid == 0 or non_interactive,
            "prefix": prefix,
            "can_install": bool(manager) and (brew or uid == 0 or non_interactive)}


def _virtualization() -> str:
    if os.environ.get("container"):
        return os.environ["container"]
    text = _read("/proc/1/cgroup", 8192)
    for needle in ("docker", "lxc", "podman", "kubepods", "containerd"):
        if needle in text:
            return needle
    if _which("systemd-detect-virt"):
        rc, text = _run(["systemd-detect-virt"], 1.5)
        if rc == 0 and text and text != "none":
            return text
    return ""


def _cpu_percent(sample_seconds: float = 0.12) -> float:
    def snapshot() -> tuple[int, int]:
        line = _read("/proc/stat", 4096).splitlines()[0]
        parts = [int(x) for x in line.split()[1:] if x.isdigit()]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts)
        return idle, total
    try:
        idle1, total1 = snapshot()
        time.sleep(max(0.0, sample_seconds))
        idle2, total2 = snapshot()
        delta = total2 - total1
        return round(max(0.0, min(100.0, (1 - (idle2 - idle1) / delta) * 100)), 1) \
            if delta > 0 else 0.0
    except (IndexError, ValueError):
        return 0.0


def _uptime() -> float:
    try:
        return float(_read("/proc/uptime").split()[0])
    except (IndexError, ValueError):
        return 0.0


def _load_average() -> list[float]:
    try:
        return [float(x) for x in _read("/proc/loadavg").split()[:3]]
    except (ValueError, IndexError):
        return [0.0, 0.0, 0.0]


def _tools(names: list[str]) -> dict[str, str]:
    return {name: (_which(name) or "") for name in names}


def _all_tool_names() -> list[str]:
    names: set[str] = set()
    for chain in BACKEND_CHAINS.values():
        names.update(chain)
    for tool in PACKAGE_MAP:
        names.add(tool)
    for group in READINESS_GROUPS:
        names.update(group["tools"])
    return sorted(names)


class SystemProfile:
    """A snapshot of this machine plus the adaptation decisions derived from it."""

    def __init__(self, data: dict | None = None):
        self.data = data or self.detect()

    # ------------------------------------------------------------- detection
    @classmethod
    def detect(cls) -> dict:
        osrel = _parse_os_release()
        manager = _package_manager()
        privilege = _privilege(manager)
        desktop = _desktop()
        mem = _meminfo()
        system = platform.system() or "Linux"
        data = {
            "generated": time.time(),
            "host": socket.gethostname(),
            "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "",
            "shell": os.environ.get("SHELL") or "",
            "os": {
                "system": system,
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "kernel": platform.release(),
                "distro": osrel.get("ID", ""),
                "distro_name": osrel.get("PRETTY_NAME") or osrel.get("NAME", system),
                "distro_version": osrel.get("VERSION_ID", ""),
                "family": "debian" if osrel.get("ID_LIKE", "").find("debian") >= 0
                          else osrel.get("ID", ""),
            },
            "init": _init_system(),
            "package_manager": manager,
            "privilege": privilege,
            "virtualization": _virtualization(),
            "desktop": desktop,
            "audio": {
                "pipewire": bool(_which("pw-cli") or _which("wpctl")),
                "pulseaudio": bool(_which("pactl") or _which("pulseaudio")),
                "alsa": bool(_which("amixer")),
            },
            "cpu": {
                "model": _cpu_model(),
                "cores": os.cpu_count() or 1,
                "architecture": platform.machine(),
            },
            "memory": {
                "total": mem.get("MemTotal", 0),
                "available": mem.get("MemAvailable", 0),
                "swap_total": mem.get("SwapTotal", 0),
                "swap_free": mem.get("SwapFree", 0),
            },
            "disk": {
                "root": _disk("/"),
                "home": _disk(Path.home()),
            },
            "gpu": _gpu(),
            "battery": _battery(),
            "network": _network(),
            "tools": _tools(_all_tool_names()),
            "locale": {"lang": os.environ.get("LANG", ""),
                       "timezone": _read("/etc/timezone").strip()},
            "backends": {cap: _first(chain) for cap, chain in BACKEND_CHAINS.items()},
        }
        data["readiness"] = cls._readiness(data)
        data["adaptation"] = cls._adaptation(data)
        data["score"] = cls._score(data)
        data["fingerprint"] = cls.fingerprint_of(data)
        return data

    @staticmethod
    def _readiness(data: dict) -> list[dict]:
        tools = data.get("tools") or {}
        manager = (data.get("package_manager") or {}).get("name", "")
        privilege = data.get("privilege") or {}
        out = []
        for group in READINESS_GROUPS:
            present = [t for t in group["tools"] if tools.get(t)]
            missing = [t for t in group["tools"] if not tools.get(t)]
            status = "ready" if present else "missing"
            if present and len(present) < len(group["tools"]) and group["id"] in (
                    "files.archive", "system.monitoring"):
                status = "degraded"
            packages = []
            if missing and manager:
                for tool in missing:
                    pkg = (PACKAGE_MAP.get(tool) or {}).get(manager)
                    if pkg and pkg not in packages:
                        packages.append(pkg)
            out.append({
                "id": group["id"], "label": group["label"],
                "category": group["category"], "status": status,
                "backend": present[0] if present else "",
                "present": present, "missing": missing,
                "packages": packages if privilege.get("can_install") else packages,
                "can_install": bool(packages) and bool(privilege.get("can_install")),
                "hint": group["hint"],
            })
        return out

    @staticmethod
    def _adaptation(data: dict) -> list[dict]:
        items = []
        for row in data.get("readiness") or []:
            if row["status"] == "ready" or not row.get("packages"):
                continue
            items.append({
                "capability": row["id"],
                "label": row["label"],
                "missing": row["missing"],
                "packages": row["packages"],
                "installable": row["can_install"],
                "hint": row["hint"],
            })
        items.sort(key=lambda item: (not item["installable"], item["capability"]))
        return items

    @staticmethod
    def _score(data: dict) -> dict:
        rows = data.get("readiness") or []
        ready = sum(1 for row in rows if row["status"] == "ready")
        degraded = sum(1 for row in rows if row["status"] == "degraded")
        total = len(rows) or 1
        return {"total": len(rows), "ready": ready, "degraded": degraded,
                "missing": len(rows) - ready - degraded,
                "percent": round((ready + 0.5 * degraded) / total * 100)}

    @staticmethod
    def fingerprint_of(data: dict) -> str:
        keep = {
            "os": data.get("os"),
            "desktop": data.get("desktop"),
            "init": data.get("init"),
            "package_manager": (data.get("package_manager") or {}).get("name"),
            "backends": data.get("backends"),
            "cpu": (data.get("cpu") or {}).get("model"),
        }
        return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:16]

    # ---------------------------------------------------------------- access
    @property
    def fingerprint(self) -> str:
        return str(self.data.get("fingerprint") or self.fingerprint_of(self.data))

    def backend(self, capability: str) -> dict:
        chain = BACKEND_CHAINS.get(capability, [])
        tools = self.data.get("tools") or {}
        for tool in chain:
            if tools.get(tool):
                return {"capability": capability, "tool": tool,
                        "path": tools[tool], "available": True}
        return {"capability": capability, "tool": "", "path": "",
                "available": False, "requires": chain}

    def tool(self, name: str) -> str:
        return str((self.data.get("tools") or {}).get(name) or "")

    def has(self, *names: str) -> bool:
        return all(bool(self.tool(name)) for name in names)

    def package_for(self, tool: str) -> str:
        manager = (self.data.get("package_manager") or {}).get("name", "")
        return (PACKAGE_MAP.get(tool) or {}).get(manager, "")

    def install_command(self, packages: list[str]) -> list[str]:
        manager = self.data.get("package_manager") or {}
        if not manager or not packages:
            return []
        prefix = list((self.data.get("privilege") or {}).get("prefix") or [])
        return prefix + list(manager.get("install") or []) + list(packages)

    def readiness(self) -> list[dict]:
        return list(self.data.get("readiness") or [])

    def adaptation(self) -> list[dict]:
        return list(self.data.get("adaptation") or [])

    # --------------------------------------------------------------- metrics
    def metrics(self, sample_seconds: float = 0.12) -> dict:
        mem = _meminfo()
        total = mem.get("MemTotal", 0) or 0
        available = mem.get("MemAvailable", 0) or 0
        swap_total = mem.get("SwapTotal", 0) or 0
        swap_free = mem.get("SwapFree", 0) or 0
        disk_root = _disk("/")
        disk_home = _disk(Path.home())
        battery = _battery()
        temps = _temperatures()
        load = _load_average()
        net = self.data.get("network") or {}
        return {
            "ts": time.time(),
            "cpu_percent": _cpu_percent(sample_seconds),
            "cpu_cores": os.cpu_count() or 1,
            "load": load,
            "mem_total": total,
            "mem_available": available,
            "mem_used_percent": round((total - available) / total * 100, 1)
                                if total else 0.0,
            "swap_total": swap_total,
            "swap_used_percent": round((swap_total - swap_free) / swap_total * 100, 1)
                                 if swap_total else 0.0,
            "disk_root": disk_root,
            "disk_home": disk_home,
            "disk_free_percent": disk_root["free"] / (disk_root["total"] or 1) * 100,
            "battery": battery,
            "battery_percent": battery.get("percent"),
            "on_battery": bool(battery.get("on_battery")),
            "temperatures": temps,
            "max_temp_c": max((t["celsius"] for t in temps), default=None),
            "uptime": _uptime(),
            "wifi_connected": bool((net.get("wifi") or {}).get("connected")),
            "network_up": any(i.get("state") == "up"
                              for i in (net.get("interfaces") or [])),
        }

    # ------------------------------------------------------------ comparison
    def diff(self, previous: dict | None) -> dict:
        if not previous:
            return {"first_run": True}
        changes: dict[str, Any] = {}
        for key in ("os", "desktop", "init", "package_manager", "gpu",
                    "network", "backend", "backends"):
            if previous.get(key) != self.data.get(key):
                changes[key] = {"before": previous.get(key), "after": self.data.get(key)}
        old_tools = set(k for k, v in (previous.get("tools") or {}).items() if v)
        new_tools = set(k for k, v in (self.data.get("tools") or {}).items() if v)
        if old_tools != new_tools:
            changes["tools_added"] = sorted(new_tools - old_tools)
            changes["tools_removed"] = sorted(old_tools - new_tools)
        return changes or {"changed": False}

    def summary(self) -> str:
        o = self.data.get("os") or {}
        d = self.data.get("desktop") or {}
        c = self.data.get("cpu") or {}
        score = self.data.get("score") or {}
        return (f"{o.get('distro_name') or o.get('system')} · {c.get('cores')} jeder · "
                f"{d.get('kind')} · pripravljenost {score.get('percent', 0)}%")


# Module-level cache for cheap repeated access inside one process.
_CACHE: dict[str, Any] = {"ts": 0.0, "profile": None}


def get_profile(refresh: bool = False, ttl: float = 300.0) -> SystemProfile:
    now = time.time()
    profile = _CACHE.get("profile")
    if (not refresh and profile is not None
            and now - float(_CACHE.get("ts") or 0) < ttl):
        return profile
    profile = SystemProfile()
    _CACHE["profile"] = profile
    _CACHE["ts"] = now
    return profile
