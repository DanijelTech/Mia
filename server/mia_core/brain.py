"""Chat-vs-agent routing for the split brain.

Pure stdlib: no network, no heavy imports. The deterministic command router
(`mia_core.autonomy.intents`) runs before this; `classify_brain` only decides
whether a remaining turn belongs to the fast chat model or to Hermes.
"""

from __future__ import annotations

import re

from .integration import detect_intent
from .recipes import normalize

_AGENT_VERBS = frozenset({
    "odpri", "odprite", "zapri", "zaprite", "zazeni", "pozeni", "ustvari",
    "izbrisi", "premakni", "kopiraj", "preimenuj", "shrani", "preberi",
    "poslji", "nastavi", "spremeni", "poklici", "prenesi", "namesti",
    "posodobi", "vklopi", "izklopi", "zaustavi", "ustavi",
    "open", "launch", "run", "start", "stop", "close", "search", "find",
    "read", "write", "save", "send", "set", "change", "download", "install",
    "update", "delete", "remove", "move", "copy", "rename", "show", "check",
    "play", "pause", "mute", "unmute",
})

_LIVE_DATA = frozenset({
    "vreme", "vremenska", "napoved", "temperatura", "novice", "cena", "cene",
    "tecaj", "delnica", "promet", "guzva", "let", "leti", "vlak", "vlaki",
    "avtobus", "dostava", "sledenje", "status", "stanje", "baterija",
    "weather", "news", "price", "stock", "traffic", "flight",
})

_AGENT_URL_RE = re.compile(r"https?://|www\.", re.I)
_AGENT_PATH_RE = re.compile(r"(?:^|[\s\"(])(?:~?/|\./|\.\./|[A-Za-z]:\\)")


def classify_brain(text: str) -> str:
    """Return ``"agent"`` when a turn needs tools/live data, else ``"chat"``.

    Conservative: unknown phrasing goes to the fast chat model; explicit
    actions, live-data questions, URLs and paths go to the agent.
    """
    raw = re.sub(r"^\s*(?:\[[^\]]*\]\s*)+", "", (text or "").strip())
    if not raw:
        return "chat"
    tokens = set(normalize(raw))
    if tokens & _AGENT_VERBS or tokens & _LIVE_DATA:
        return "agent"
    if _AGENT_URL_RE.search(raw) or _AGENT_PATH_RE.search(raw):
        return "agent"
    if detect_intent(raw) != "chat":
        return "agent"
    return "chat"
