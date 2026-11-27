"""Deterministic natural-language router for machine tasks.

Everyday commands must work without an LLM: it is faster, it works offline, and
the answer is predictable. This router recognises Slovenian (and the English
forms people actually mix in) and returns a structured `Intent`. The service
executes it through `mia-ctl` or the planner, so policy and audit still apply.

The router is deliberately conservative: a sentence is only hijacked when it
starts with a command verb or contains an unambiguous system phrase. Anything
else returns None and continues to the agent.
"""

from __future__ import annotations

import datetime as _dt
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .. import i18n
from ..integration import time_answer

_FOLD = str.maketrans("čćšžđČĆŠŽĐ", "ccszdCCSZD")


def fold(text: str) -> str:
    """Lowercase + strip Slovenian diacritics while preserving string length."""
    return (text or "").translate(_FOLD).lower()


_POLITE = re.compile(
    r"^(?:(?:mia|mijo|mija|mio|sefe|prosim|te|mi|potem|zdaj|sedaj)\b[,;:]?\s*)+")
_TRAIL = " .,!?:;"


def _clean(value: str) -> str:
    value = (value or "").strip(_TRAIL)
    while _POLITE.match(value):
        value = _POLITE.sub("", value).strip(_TRAIL)
    return value


@dataclass
class Intent:
    name: str
    kind: str = "query"          # query|action|plan|schedule|cancel_job|confirm|cancel|help
    verb: str = ""
    args: dict = field(default_factory=dict)
    reply: str = ""
    confirmation: bool = False
    destructive: bool = False
    plan: dict | None = None
    trigger: dict | None = None
    confidence: float = 0.9
    text: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "verb": self.verb,
                "args": self.args, "reply": self.reply,
                "confirmation": self.confirmation,
                "destructive": self.destructive,
                "trigger": self.trigger, "confidence": self.confidence}


_LONG = 28  # tokens; longer utterances are conversations, not commands


def _too_long(flat: str) -> bool:
    return len(flat.split()) > _LONG


def _action(name: str, verb: str, *, args: dict | None = None,
            reply: str = "", confirmation: bool = False,
            destructive: bool = False, text: str = "") -> Intent:
    return Intent(name=name, kind="action", verb=verb, args=args or {},
                  reply=reply, confirmation=confirmation,
                  destructive=destructive, text=text)


def _query(name: str, **args: Any) -> Intent:
    return Intent(name=name, kind="query", args=args)


_DURATION_UNITS = {
    "sekund": 1, "sekunde": 1, "sekundo": 1, "sek": 1, "s": 1,
    "minut": 60, "minute": 60, "minuto": 60, "min": 60,
    "ur": 3600, "ure": 3600, "uro": 3600, "h": 3600,
    "dni": 86400, "dan": 86400, "dneva": 86400,
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minutes": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hrs": 3600,
    "day": 86400, "days": 86400,
}
_DURATION_RE = re.compile(
    r"(?:(?:cez|za|in)\s+(\d+)\s*"
    r"(sekund\w*|sekunde|sekundo|sek|second\w*|secs?|minut\w*|minute|minuto|min"
    r"|minutes?|mins?|ur\w*|ure|uro|hours?|hrs?|dni|dan|dneva|days?))", re.I)


def _duration_seconds(flat: str) -> int | None:
    match = _DURATION_RE.search(flat)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    for prefix, seconds in _DURATION_UNITS.items():
        if unit.startswith(prefix):
            return amount * seconds
    return None


def _clock(flat: str) -> tuple[int, int] | None:
    match = re.search(r"\bob\s+(\d{1,2})(?::(\d{2}))?\s*(?:h|uro|uri|zjutraj|"
                      r"opoldne|popoldne|zvecer|ponoci)?\b", flat)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if "popoldne" in flat or "zvecer" in flat or "ponoci" in flat:
        if hour < 12:
            hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _next_clock(hour: int, minute: int) -> float:
    now = _dt.datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() <= now.timestamp() + 1:
        candidate += _dt.timedelta(days=1)
    return candidate.timestamp()


# --------------------------------------------------------------------- rules
_RULES: list[tuple[re.Pattern, Any]] = []


def _rule(pattern: str):
    def deco(fn):
        _RULES.append((re.compile(pattern, re.I), fn))
        return fn
    return deco


# --------------------------------------------------------------- confirmation
@_rule(r"^(?:ja|da|izvrsi|potrdi|potrjujem|seveda|ja prosim)\b")
def _confirm(m, text, flat):
    return Intent(name="confirm", kind="confirm", reply="")


@_rule(r"^(?:ne|ne hvala|preklici|preklic|ne naredi|nic ne naredi|"
       r"odnehaj|pozabi)\b(?!\s+(?:opomnik|opravilo|nalogo|job))")
def _cancel(m, text, flat):
    return Intent(name="cancel", kind="cancel", reply="")


@_rule(r"^(?:pomoc|help|kaj lahko naredis|kaj znas|kateri ukazi|seznam ukazov)")
def _help(m, text, flat):
    return Intent(name="help", kind="help")


# -------------------------------------------------------------------- time
@_rule(r"(?:koliko je (?:ura|uro)|kaj je ura|kaksna je ura|povej mi uro|"
       r"what time is it|what is the time)")
def _time(m, text, flat):
    answer = time_answer(text, lang=i18n.current_lang())
    return Intent(name="time", kind="query", reply=answer or "")


@_rule(r"(?:kateri dan je|kateri datum|kaksen dan je|kateri dan smo|"
       r"danes je kateri|what is the date|what day is it)")
def _date(m, text, flat):
    answer = time_answer(text, lang=i18n.current_lang())
    return Intent(name="date", kind="query", reply=answer or "")


# --------------------------------------------------------------- resources
@_rule(r"(?:koliko (?:je )?(?:prostega |zasedenega )?(?:ram|pomnilnika|"
       r"diska|prostora|cpu|procesorja|baterije)|kaksna je poraba|"
       r"poraba (?:virov|cpu|ram)|obremenitev|kako je s (?:viro|prostor)|"
       r"koliko prostora|temperature|kako vroca|"
       r"how much (?:ram|memory|disk|cpu)|resource usage)")
def _resources(m, text, flat):
    return _query("resources", detail=flat)


@_rule(r"(?:kateri sistem|kaksen (?:racunalnik|sistem)|specifikacije|"
       r"kaj imas (?:za sistem|notri)|sistemske informacije|"
       r"which system|system info)")
def _sysinfo(m, text, flat):
    return _query("sysinfo")


@_rule(r"(?:ali si zdrava|zdravje|stanje sistema|kako si|si v redu|"
       r"health|system health|je vse v redu)")
def _health(m, text, flat):
    return _query("health")


@_rule(r"(?:kaj podpiras|katere zmogljivosti|kaj znas|zmogljivosti|"
       r"kaj lahko naredis na tem racunalniku|what can you do|capabilities)")
def _capabilities(m, text, flat):
    return _query("capabilities")


@_rule(r"(?:kaj si avtomatizirala|katere avtomatizacije|avtomatizacije|"
       r"katere naloge imas|urnik|kateri opravki|"
       r"what automations|scheduled jobs)")
def _jobs(m, text, flat):
    return _query("jobs")


@_rule(r"(?:zadnje naloge|katere naloge si izvajala|zgodovina nalog|"
       r"recent tasks|task history)")
def _tasks(m, text, flat):
    return _query("tasks")


@_rule(r"(?:kaj je narobe|napake|alarmi|opozorila|"
       r"which errors|alerts)")
def _alerts(m, text, flat):
    return _query("alerts")


# ------------------------------------------------------------------ volume
@_rule(r"^(?:(?:nastavi|daj|naredi)\s+)?glasnost(?:i)?\s+(?:na\s+)?(\d{1,3})")
def _volume_set(m, text, flat):
    return _action("volume.set", "volume",
                   args={"action": "set", "value": int(m.group(1))},
                   reply=f"Glasnost {m.group(1)}.")


@_rule(r"^(?:set|change)\s+volume\s+(?:to\s+)?(\d{1,3})|^volume\s+(?:to\s+)?(\d{1,3})")
def _volume_set_en(m, text, flat):
    value = m.group(1) or m.group(2)
    return _action("volume.set", "volume",
                   args={"action": "set", "value": int(value)},
                   reply=f"Glasnost {value}.")


@_rule(r"^(?:koliko je glasnosti|kaksna je glasnost|glasnost status|"
       r"volume status)")
def _volume_status(m, text, flat):
    return _action("volume.status", "volume", args={"action": "status"},
                   reply="")


@_rule(r"^(?:pojacaj|glasneje|bolj glasno|povecaj glasnost)(?:\s+za\s+(\d+))?")
def _volume_up(m, text, flat):
    value = int(m.group(1)) if m.group(1) else None
    return _action("volume.up", "volume",
                   args={"action": "up", "value": value}, reply="Pojačano.")


@_rule(r"^(?:zmanjsaj|znizaj|tise|manj glasno|zmansaj glasnost)(?:\s+za\s+(\d+))?")
def _volume_down(m, text, flat):
    value = int(m.group(1)) if m.group(1) else None
    return _action("volume.down", "volume",
                   args={"action": "down", "value": value}, reply="Zmanjšano.")


@_rule(r"^(?:utisaj|mute|brez zvoka|ugasni zvok)")
def _volume_mute(m, text, flat):
    return _action("volume.mute", "volume", args={"action": "mute"},
                   reply="Utišano.")


@_rule(r"^(?:odkleni zvok|unmute|vrni zvok)")
def _volume_unmute(m, text, flat):
    return _action("volume.unmute", "volume", args={"action": "unmute"},
                   reply="Zvok vklopljen.")


# -------------------------------------------------------------- brightness
@_rule(r"^(?:nastavi|daj)\s+svetlost\s+(?:na\s+)?(\d{1,3})")
def _brightness_set(m, text, flat):
    return _action("brightness.set", "brightness",
                   args={"action": "set", "value": int(m.group(1))},
                   reply=f"Svetlost {m.group(1)}.")


@_rule(r"^(?:pojacaj svetlost|bolj svetlo|svetlejse)")
def _brightness_up(m, text, flat):
    return _action("brightness.up", "brightness", args={"action": "up"},
                   reply="Svetlost povečana.")


@_rule(r"^(?:zmanjsaj svetlost|manj svetlo|temnise|potemni)")
def _brightness_down(m, text, flat):
    return _action("brightness.down", "brightness", args={"action": "down"},
                   reply="Svetlost zmanjšana.")


# ------------------------------------------------------------------- media
@_rule(r"^(?:predvajaj|zaigraj|play)\s*(?:glasbo|muziko|pesem|music|song)?\s*$")
def _media_play(m, text, flat):
    return _action("media.play", "media", args={"action": "play"},
                   reply="Predvajam.")


@_rule(r"^(?:ustavi|ustavite|zaustavi|prekini|prekinite|ugasni|ugasnite|"
       r"zapri|zaprite|close|stop)\s+"
       r"(?:vsa\s+|vse\s+|oba\s+|obe\s+)?(?:okna\s+|okno\s+)?(?:na\s+)?"
       r"(?:the\s+|a\s+|an\s+)?"
       r"(?:youtube|jutub|yt|glasb\w*|muzik\w*|glazb\w*|pesem|pesmi|"
       r"predvajanje|video|film|music|song)\b")
def _media_close(m, text, flat):
    return _action("media.close", "media", args={"action": "close"},
                   reply="Zapiram predvajanje.")


@_rule(r"^(?:pavziraj|pavza|pause|ustavi predvajanje|ustavi glasbo)\b")
def _media_pause(m, text, flat):
    return _action("media.pause", "media", args={"action": "pause"},
                   reply="Pavza.")


@_rule(r"^(?:naslednja|naslednjo)\s+(?:pesem|skladbo|track)|^(?:next|naslednji)$")
def _media_next(m, text, flat):
    return _action("media.next", "media", args={"action": "next"},
                   reply="Naslednja.")


@_rule(r"^(?:prejsnja|prejsnjo)\s+(?:pesem|skladbo)|^(?:previous|prejsnji)$")
def _media_previous(m, text, flat):
    return _action("media.previous", "media", args={"action": "previous"},
                   reply="Prejšnja.")


@_rule(r"(?:kaj se predvaja|katera pesem|trenutna pesem|now playing)")
def _media_status(m, text, flat):
    return _action("media.status", "media", args={"action": "status"})


# ------------------------------------------------------------------- power
@_rule(r"^(?:zakleni|lock)\s*(?:zaslon|racunalnik|se|screen|computer)?")
def _power_lock(m, text, flat):
    return _action("power.lock", "power", args={"action": "lock"},
                   reply="Zaklenjeno, šefe.")


@_rule(r"^(?:spanje|suspend|pojdi spat|daj na spanje|sleep)")
def _power_suspend(m, text, flat):
    return _action("power.suspend", "power", args={"action": "suspend"},
                   confirmation=True, destructive=True,
                   reply="Naj se ustavim? Potrdi s »ja«.")


@_rule(r"^(?:restart(?:aj)?|reboot|ponovno zazeni)"
       r"(?:\s+(?:racunalnik|sistem|napravo|stroj|computer|machine))?$")
def _power_reboot(m, text, flat):
    return _action("power.reboot", "power", args={"action": "reboot"},
                   confirmation=True, destructive=True,
                   reply="Naj ponovno zaženem računalnik? Potrdi s »ja«.")


@_rule(r"^(?:ugasni|shutdown|izklopi racunalnik|ugasni racunalnik)")
def _power_shutdown(m, text, flat):
    return _action("power.shutdown", "power", args={"action": "shutdown"},
                   confirmation=True, destructive=True,
                   reply="Naj ugasnem računalnik? Potrdi s »ja«.")


# -------------------------------------------------------------- screenshot
@_rule(r"^(?:posnemi|naredi posnetek|screenshot|screen shot|take a screenshot|"
       r"take screenshot|capture)\s*(?:zaslon|ekran|screen)?")
def _screenshot(m, text, flat):
    return _action("screenshot", "screenshot", args={},
                   reply="Posnetek shranjen.")


# --------------------------------------------------------------- clipboard
@_rule(r"^(?:kopiraj|premakni|prestavi|preimenuj)\s+(?:datoteko\s+|mapo\s+)?"
       r"(.+?)\s+v\s+(.+)$")
def _files_transfer(m, text, flat):
    verb = fold(text.split()[0])
    src = _clean(text[m.start(1):m.end(1)])
    dst = _clean(text[m.start(2):m.end(2)])
    name = {"kopiraj": "files.copy", "premakni": "files.move",
            "prestavi": "files.move", "preimenuj": "files.rename"}[verb]
    action = name.split(".")[1]
    return _action(name, "files",
                   args={"action": action, "src": src, "dst": dst},
                   confirmation=action in ("move", "rename"),
                   destructive=action in ("move", "rename"),
                   reply=(f"Naj premaknem {src} v {dst}? Potrdi s »ja«."
                          if action == "move" else
                          f"Naj preimenujem {src} v {dst}? Potrdi s »ja«."
                          if action == "rename" else f"Kopiram v {dst}."))


@_rule(r"^(?:preberi|povej)\s+(?:mi\s+)?(?:kaj je v\s+)?odlozisce")
def _clipboard_get(m, text, flat):
    return _action("clipboard.get", "clipboard", args={"action": "get"})


@_rule(r"^(?:kopiraj|shrani v odlozisce|nastavi odlozisce na)\s+(.+)$")
def _clipboard_set(m, text, flat):
    value = _clean(text[m.start(1):m.end(1)])
    return _action("clipboard.set", "clipboard",
                   args={"action": "set", "text": value},
                   reply="Kopirano.")


# ----------------------------------------------------------- open / close
_URL = re.compile(r"^(?:https?://|www\.)\S+", re.I)


@_rule(r"^(?:odpri|odprite|open|zazeni|launch)\s+(.+)$")
def _open(m, text, flat):
    target = _clean(text[m.start(1):m.end(1)])
    target = re.sub(r"^(?:the|a|an)\s+", "", target, flags=re.I)
    folded = fold(target)
    if folded in ("brskalnik", "browser", "splet", "internet"):
        return _action("open.url", "open", args={"target": "browser"},
                       reply="Odpiram brskalnik.")
    if _URL.match(target):
        url = target if re.match(r"^https?://", target, re.I) else "https://" + target
        return _action("open.url", "open", args={"target": url},
                       reply="Odpiram.")
    if "." in target and " " not in target and "/" not in target:
        return _action("open.url", "open",
                       args={"target": "https://" + target},
                       reply="Odpiram.")
    return _action("apps.launch", "apps", args={"action": "launch",
                                                "name": target},
                   reply=f"Odpiram {target}.")


@_rule(r"^(?:zapri|close|quit|ugasni)\s+(?!racunalnik|sistem|zvok|glasb|proces|storitev)"
       r"(?:aplikacijo\s+|program\s+)?(.+)$")
def _close(m, text, flat):
    target = _clean(text[m.start(1):m.end(1)])
    if target in ("okno", "okna", "vse", "vsa okna"):
        return _action("window.close_all", "window", args={"name": ""},
                       reply="Zapiram okna?")
    return _action("apps.quit", "apps", args={"action": "quit",
                                              "name": target},
                   reply=f"Zapiram {target}.")


@_rule(r"^(?:preklopi|fokusiraj|focus|pojdi)\s+(?:na\s+)?(?:okno\s+|aplikacijo\s+)?(.+)$")
def _window_focus(m, text, flat):
    target = _clean(text[m.start(1):m.end(1)])
    return _action("window.focus", "window", args={"name": target},
                   reply=f"Preklopim na {target}.")


@_rule(r"^(?:minimiziraj|pomanjsaj|minimize)\s+(.+)$")
def _window_minimize(m, text, flat):
    target = _clean(text[m.start(1):m.end(1)])
    return _action("window.minimize", "window", args={"name": target},
                   reply="Minimizirano.")


@_rule(r"^(?:maksimiziraj|povecaj okno|maximize)\s+(.+)$")
def _window_maximize(m, text, flat):
    target = _clean(text[m.start(1):m.end(1)])
    return _action("window.maximize", "window", args={"name": target},
                   reply="Maksimizirano.")


@_rule(r"^(?:katera|kateri|seznam)\s+okna|^(?:kaj je odprto|odprta okna|"
       r"windows list|which windows)")
def _windows_list(m, text, flat):
    return _action("window.list", "window", args={})


# --------------------------------------------------------------- processes
@_rule(r"^(?:kateri|kaksni|seznam)\s+procesi|^kaj tece|^top procesi|"
       r"^process list")
def _process_list(m, text, flat):
    return _action("process.list", "process", args={"action": "list"})


@_rule(r"^(?:najdi|poisci|find)\s+proces\s+(.+)$")
def _process_find(m, text, flat):
    name = _clean(text[m.start(1):m.end(1)])
    return _action("process.find", "process",
                   args={"action": "find", "name": name})


@_rule(r"^(?:ustavi|ubij|kill|koncaj)\s+proces\s+(.+)$")
def _process_kill(m, text, flat):
    name = _clean(text[m.start(1):m.end(1)])
    return _action("process.kill", "process",
                   args={"action": "kill", "name": name},
                   confirmation=True, destructive=True,
                   reply=f"Naj ustavim proces {name}? Potrdi s »ja«.")


# ---------------------------------------------------------------- services
@_rule(r"^(?:ali\s+)?(?:tece|deluje|je aktiven)\s+(?:storitev\s+)?"
       r"(?:storitev\s+)?([a-z0-9@_.-]+)")
def _service_status(m, text, flat):
    unit = m.group(1)
    if unit in ("vse", "sistem", "racunalnik"):
        return None
    return _action("service.status", "service",
                   args={"action": "status", "unit": unit})


@_rule(r"^(?:stanje|status)\s+(?:storitve\s+)?([a-z0-9@_.-]+)$")
def _service_status2(m, text, flat):
    return _action("service.status", "service",
                   args={"action": "status", "unit": m.group(1)})


@_rule(r"^(?:ponovno zazeni|restartaj|restart)\s+(?:storitev\s+|servis\s+)?"
       r"([a-z0-9@_.-]+)")
def _service_restart(m, text, flat):
    unit = m.group(1)
    if fold(unit) in ("racunalnik", "sistem", "napravo", "stroj",
                      "computer", "machine"):
        return None
    return _action("service.restart", "service",
                   args={"action": "restart", "unit": unit},
                   confirmation=True, destructive=True,
                   reply=f"Naj ponovno zaženem storitev {unit}? Potrdi s »ja«.")


@_rule(r"^(?:ustavi|stop)\s+(?:storitev\s+|servis\s+)([a-z0-9@_.-]+)")
def _service_stop(m, text, flat):
    unit = m.group(1)
    return _action("service.stop", "service",
                   args={"action": "stop", "unit": unit},
                   confirmation=True, destructive=True,
                   reply=f"Naj ustavim storitev {unit}? Potrdi s »ja«.")


# ------------------------------------------------------------------- files
@_rule(r"^(?:najdi|poisci|find)\s+(?:datoteko|file|mapo)\s+(.+)$")
def _files_search(m, text, flat):
    query = _clean(text[m.start(1):m.end(1)])
    return _action("files.search", "files", args={"action": "search", "query": query})


@_rule(r"^(?:katere|zadnje|najnovejse)\s+(?:datoteke|files)|^nedavne datoteke|"
       r"^recent files")
def _files_recent(m, text, flat):
    return _action("files.recent", "files", args={"action": "recent"})


@_rule(r"^(?:odpri|open)\s+(?:datoteko|file)\s+(.+)$")
def _files_open(m, text, flat):
    path = _clean(text[m.start(1):m.end(1)])
    return _action("files.open", "files", args={"action": "open", "path": path})


@_rule(r"^(?:ustvari|naredi)\s+(?:novo\s+)?(?:mapo|imenik|direktorij)\s+(.+)$")
def _files_mkdir(m, text, flat):
    path = _clean(text[m.start(1):m.end(1)])
    return _action("files.mkdir", "files", args={"action": "mkdir", "path": path},
                   reply=f"Ustvarjam mapo {path}.")


@_rule(r"^(?:vrzi v smeti|premakni v smeti|shrani v smeti)\s+(.+)$")
def _files_trash(m, text, flat):
    path = _clean(text[m.start(1):m.end(1)])
    return _action("files.trash", "files", args={"action": "trash", "path": path},
                   confirmation=True, destructive=True,
                   reply=f"Naj premaknem {path} v smeti? Potrdi s »ja«.")


@_rule(r"^(?:izbrisi|zbrisi|delete)\s+(?:datoteko\s+|mapo\s+)?(.+)$")
def _files_delete(m, text, flat):
    path = _clean(text[m.start(1):m.end(1)])
    return _action("files.delete", "files", args={"action": "delete", "path": path},
                   confirmation=True, destructive=True,
                   reply=f"Naj trajno izbrišem {path}? Potrdi s »ja«.")


@_rule(r"^(?:stisni|arhiviraj|zapakiraj)\s+(.+?)\s+v\s+(.+)$")
def _files_archive(m, text, flat):
    src = _clean(text[m.start(1):m.end(1)])
    dst = _clean(text[m.start(2):m.end(2)])
    return _action("files.archive", "files", args={"action": "archive", "src": src, "dst": dst},
                   reply=f"Arhiviram v {dst}.")


@_rule(r"^(?:razsiri|odpakiraj|ekstrahiraj)\s+(.+?)\s+v\s+(.+)$")
def _files_extract(m, text, flat):
    archive = _clean(text[m.start(1):m.end(1)])
    dest = _clean(text[m.start(2):m.end(2)])
    return _action("files.extract", "files",
                   args={"action": "extract", "archive": archive, "dest": dest},
                   reply=f"Razširjam v {dest}.")


@_rule(r"^(?:koliko je velika|velikost)\s+(?:mapa|datoteka|mape|datoteke)?\s*(.+)$")
def _files_du(m, text, flat):
    path = _clean(text[m.start(1):m.end(1)]) or "~"
    return _action("files.du", "files", args={"action": "du", "path": path})


@_rule(r"^(?:najdi|poisci)\s+velike datoteke|^velike datoteke|^large files")
def _files_large(m, text, flat):
    return _action("files.large", "files", args={"action": "large"})


@_rule(r"^(?:pocisti|ocisti)\s+(?:smeti|temp|zasutne|disk|prostor)|"
       r"^clean(?:up)? (?:temp|disk)")
def _files_cleanup(m, text, flat):
    return Intent(name="plan.cleanup", kind="plan", verb="cleanup",
                  args={"template": "cleanup"}, text=text,
                  confirmation=True, destructive=True,
                  reply="Naj počistim temp datoteke in poiščem velike datoteke? Potrdi s »ja«.")


# ----------------------------------------------------------------- network
@_rule(r"^(?:kaksno je omrezje|stanje omrezja|ali imas internet|ip naslov|"
       r"network status|omrezje status)")
def _net_status(m, text, flat):
    return _action("net.status", "net")


@_rule(r"^(?:katera|kaksna)\s+(?:wifi|brezzicna)\s+omrezja|^wifi omrezja|"
       r"^seznam wifi|^wifi list")
def _wifi_list(m, text, flat):
    return _action("net.wifi-list", "net", args={"action": "wifi-list"})


@_rule(r"^(?:povezi se|poveži se|connect)\s+(?:na\s+)?(?:wifi|omrezje)\s+(.+?)"
       r"(?:\s+z geslom\s+(.+))?$")
def _wifi_connect(m, text, flat):
    ssid = _clean(text[m.start(1):m.end(1)])
    password = text[m.start(2):m.end(2)].strip() if m.group(2) else ""
    return _action("net.wifi-connect", "net",
                   args={"ssid": ssid, "password": password},
                   reply=f"Povezujem se na {ssid}.")


@_rule(r"^(?:pingaj|ping)\s+(\S+)")
def _ping(m, text, flat):
    return _action("net.ping", "net", args={"host": m.group(1)})


@_rule(r"^(?:vklopi|enable)\s+(?:pozarni zid|firewall|ufw)")
def _firewall_on(m, text, flat):
    return _action("net.firewall", "net", args={"action": "enable"},
                   confirmation=True, destructive=True,
                   reply="Naj vklopim požarni zid? Potrdi s »ja«.")


@_rule(r"^(?:izklopi|disable)\s+(?:pozarni zid|firewall|ufw)")
def _firewall_off(m, text, flat):
    return _action("net.firewall", "net", args={"action": "disable"},
                   confirmation=True, destructive=True,
                   reply="Naj izklopim požarni zid? Potrdi s »ja«.")


# ---------------------------------------------------------------- packages
@_rule(r"^(?:preveri|poglej)\s+posodobitve|^katere posodobitve|"
       r"^check (?:for )?updates")
def _pkg_updates(m, text, flat):
    return _action("pkg.list-upgradable", "pkg")


@_rule(r"^(?:posodobi sistem|posodobi racunalnik|system update|update system)")
def _pkg_update(m, text, flat):
    return Intent(name="plan.system_update", kind="plan", verb="system_update",
                  args={"template": "system_update"}, text=text,
                  confirmation=True, destructive=True,
                  reply="Naj osvežim in posodobim sistem? Potrdi s »ja«.")


@_rule(r"^(?:namesti|install)\s+(?:paket\s+|program\s+)?(.+)$")
def _pkg_install(m, text, flat):
    package = _clean(text[m.start(1):m.end(1)])
    return _action("pkg.install", "pkg", args={"packages": [package]},
                   confirmation=True, destructive=True,
                   reply=f"Naj namestim {package}? Potrdi s »ja«.")


@_rule(r"^(?:odstrani|deinstaliraj|remove|uninstall)\s+(?:paket\s+|program\s+)?(.+)$")
def _pkg_remove(m, text, flat):
    package = _clean(text[m.start(1):m.end(1)])
    return _action("pkg.remove", "pkg", args={"packages": [package]},
                   confirmation=True, destructive=True,
                   reply=f"Naj odstranim {package}? Potrdi s »ja«.")


@_rule(r"^(?:poisci|najdi)\s+paket\s+(.+)$")
def _pkg_search(m, text, flat):
    return _action("pkg.search", "pkg",
                   args={"query": _clean(text[m.start(1):m.end(1)])})


# -------------------------------------------------------------- scheduling
_REMINDER = re.compile(
    r"^(?:opomni me|opomni|remind me|spomni me)\s+"
    r"(?:(?:cez|in)\s+\d+\s*\w+\s*)?"
    r"(?:ob\s+\d{1,2}(?::\d{2})?\s*)?(?:da\s+|naj\s+|to\s+|,?\s*)(.+)$", re.I)


@_rule(r"^(?:opomni me|opomni|remind me|spomni me)\b")
def _reminder(m, text, flat):
    seconds = _duration_seconds(flat)
    clock = _clock(flat)
    if seconds:
        trigger = {"kind": "at", "ts": time.time() + seconds}
        label = f"čez {seconds} s"
    elif clock:
        trigger = {"kind": "at", "ts": _next_clock(*clock)}
        label = f"ob {clock[0]:02d}:{clock[1]:02d}"
    else:
        return None
    result = _REMINDER.search(flat)
    body = _clean(text[result.start(1):result.end(1)]) if result else ""
    body = re.sub(r"^(?:da|naj|to)\s+", "", body, flags=re.I).strip(_TRAIL)
    body = body or "Opomnik"
    return Intent(name="schedule.reminder", kind="schedule",
                  verb="reminder", trigger=trigger,
                  args={"name": f"opomnik: {body[:40]}", "body": body,
                        "label": label},
                  reply=f"V redu, opomnila te bom {label}.", text=text)


@_rule(r"^(?:vsak dan|vsakodnevno|daily)\b")
def _schedule_daily(m, text, flat):
    clock = _clock(flat)
    if not clock:
        return None
    body = re.sub(r"^(?:vsak dan|vsakodnevno|daily)\s*", "", text, flags=re.I)
    body = re.sub(r"\bob\s+\d{1,2}(?::\d{2})?\b", "", body, flags=re.I)
    body = re.sub(r"^(?:naj\s+|da\s+|,?\s*)", "", body, flags=re.I).strip(_TRAIL)
    body = body or "Dnevni opravk"
    trigger = {"kind": "daily", "time": f"{clock[0]:02d}:{clock[1]:02d}",
               "weekdays": []}
    if "delovnik" in flat or "weekday" in flat:
        trigger["weekdays"] = [0, 1, 2, 3, 4]
    return Intent(name="schedule.daily", kind="schedule", verb="daily",
                  trigger=trigger,
                  args={"name": f"dnevno: {body[:40]}", "body": body},
                  reply=f"V redu, vsak dan ob {trigger['time']}.", text=text)


@_rule(r"^(?:vsakih|every)\s+(\d+)\s*(sekund\w*|minut\w*|ur\w*|dni|dan|dneva)?")
def _schedule_every(m, text, flat):
    amount = int(m.group(1))
    unit = (m.group(2) or "sekund").lower()
    seconds = amount
    for prefix, mult in _DURATION_UNITS.items():
        if unit.startswith(prefix):
            seconds = amount * mult
            break
    body = re.sub(r"^(?:vsakih|every)\s+\d+\s*(?:sekund\w*|minut\w*|ur\w*|"
                  r"dni|dan|dneva)?\s*", "", text, flags=re.I)
    body = _clean(body) or "Redni opravk"
    trigger = {"kind": "every", "seconds": max(5, seconds)}
    return Intent(name="schedule.every", kind="schedule", verb="every",
                  trigger=trigger,
                  args={"name": f"vsakih {amount} {unit}: {body[:30]}",
                        "body": body},
                  reply=f"V redu, vsakih {amount} {unit}.", text=text)


@_rule(r"^(?:ko bo|ko se|when)\b")
def _rule_condition(m, text, flat):
    seconds = _duration_seconds(flat) or 0
    trigger: dict = {"kind": "condition", "for_seconds": seconds, "poll": 60}
    condition: dict = {}
    battery = re.search(r"baterij\w*\s+(?:pod|manj kot|below)\s+(\d+)", flat)
    disk = re.search(r"(?:prostor|disk)\w*\s+(?:pod|manj kot|below)\s+(\d+)", flat)
    memory = re.search(r"(?:ram|pomnilnik)\w*\s+(?:nad|vec kot|above)\s+(\d+)", flat)
    if battery:
        value = int(battery.group(1))
        condition = {"metric": "battery_percent", "op": "<", "value": value}
        what = f"baterija pod {value}%"
    elif "baterij" in flat and ("prazn" in flat or "nizka" in flat or "slab" in flat):
        value = 15
        condition = {"metric": "battery_percent", "op": "<", "value": value}
        what = f"baterija pod {value}%"
    elif disk:
        value = int(disk.group(1))
        condition = {"metric": "disk_free_percent", "op": "<", "value": value}
        what = f"prostega prostora pod {value}%"
    elif ("prostor" in flat or "disk" in flat) and ("poln" in flat or "zmanjk" in flat):
        value = 10
        condition = {"metric": "disk_free_percent", "op": "<", "value": value}
        what = f"prostega prostora pod {value}%"
    elif memory:
        value = int(memory.group(1))
        condition = {"metric": "mem_used_percent", "op": ">", "value": value}
        what = f"pomnilnik nad {value}%"
    elif ("pomnilnik" in flat or "ram" in flat) and "poln" in flat:
        value = 90
        condition = {"metric": "mem_used_percent", "op": ">", "value": value}
        what = f"pomnilnik nad {value}%"
    elif "se poveze" in flat or "network" in flat:
        condition = {"metric": "network_up", "op": "==", "value": 1}
        what = "omrežje se poveže"
    else:
        return None
    trigger["condition"] = condition
    body = "Opazila sem spremembo."
    cleanup = False
    if "pocisti" in flat:
        body = "Čas je za čiščenje diska."
        cleanup = True
    elif "zakleni" in flat:
        body = "Zakleni zaslon."
    elif "obvesti" in flat or "opozori" in flat:
        body = "Opozarjam te."
    return Intent(name="rule.condition", kind="schedule", verb="rule",
                  trigger=trigger,
                  args={"name": f"pravilo: {what}", "body": body,
                        "rule": True, "cleanup": cleanup},
                  reply=f"V redu, sporočila bom, ko bo {what}.", text=text)


@_rule(r"^(?:preklici|izbrisi|odstrani|delete|cancel)\s+(?:opomnik|opravilo|"
       r"nalogo|job)\s*#?(\d+)")
def _cancel_job(m, text, flat):
    return Intent(name="cancel_job", kind="cancel_job",
                  args={"job_id": int(m.group(1))},
                  reply=f"Opravilo {m.group(1)} preklicano.")


@_rule(r"^(?:delovni nacin|pripravi se za delo|work mode|delo nacin)")
def _workday(m, text, flat):
    return Intent(name="plan.workday", kind="plan", verb="workday",
                  args={"template": "workday"}, text=text,
                  reply="Pripravljam delovni način.")


@_rule(r"^(?:nocni nacin|lahko noc|nocni rezim|night mode|good night)")
def _night(m, text, flat):
    return Intent(name="plan.night", kind="plan", verb="night",
                  args={"template": "night"}, text=text,
                  confirmation=True, destructive=False,
                  reply="Preklopim v nočni način? Potrdi s »ja«.")


# --------------------------------------------------------------------- route
def route(text: str) -> Intent | None:
    raw = (text or "").strip()
    if not raw:
        return None
    flat = fold(raw)
    if _too_long(flat):
        return None
    # Polite/address prefixes are removed from the *front* so that anchored
    # command patterns still match. Fold and raw have identical length, so
    # argument spans stay valid; slice raw with the same offset.
    prefix = _POLITE.match(flat)
    offset = prefix.end() if prefix else 0
    flat_view, raw_view = flat[offset:], raw[offset:]

    def _try(rules):
        for pattern, handler in rules:
            match = pattern.search(flat_view)
            if not match:
                continue
            intent = handler(match, raw_view, flat_view)
            if intent is not None:
                if not intent.text:
                    intent.text = raw_view
                return intent
        return None

    # Anchored rules first: "vsak dan ob 8 zdravje" is a schedule, not a
    # health question, even though it contains the word "zdravje".
    anchored = [(p, h) for p, h in _RULES if p.pattern.startswith("^")]
    loose = [(p, h) for p, h in _RULES if not p.pattern.startswith("^")]
    return _try(anchored) or _try(loose)


def route_help() -> str:
    return (
        "Razumem ukaze za glasnost, svetlost, predvajanje, odprtje in zaprtje "
        "aplikacij, okna, posnetke zaslona, odložišče, datoteke, procese, "
        "storitve, omrežje, pakete, zaklep in spanje ter opomnike. "
        "Vprašaš lahko za vire, zdravje, zmogljivosti, opravila in urnik."
    )
