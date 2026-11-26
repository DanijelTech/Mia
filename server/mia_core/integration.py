"""Pure helpers that connect the voice/chat loop to the learning core.

Kept free of FastAPI, torch and network imports so it can be tested anywhere.
"""

from __future__ import annotations

import re
import time
from typing import Any

from .recipes import normalize


def _flat(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9čćžšđ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_PRAISE = (
    "tako je", "to je prav", "to je bilo prav", "zdaj je prav", "koncno prav",
    "pravilno", "odlicno", "bravo", "super", "to mi je vsec", "tocno tako",
    "hvala tako je", "ja tako", "tako se dela", "perfect", "well done",
    "that is right", "correct",
)
_CORRECTION = (
    "ni prav", "to ni prav", "to je narobe", "narobe", "ne tako", "ni bilo prav",
    "zmotila si se", "motis se", "popravi", "to ne deluje", "ne deluje tako",
    "naslednjic drugace", "raje naredi", "wrong", "not right", "incorrect",
)
_REMEMBER = (
    "zapomni si postopek", "zapomni si to", "zapomni si kako", "zapomni si nacin",
    "shrani recept", "shrani postopek", "naslednjic naredi tako",
    "to je pravi postopek", "to je pravi nacin", "remember this procedure",
    "save this recipe", "remember how you did this",
)


def detect_feedback(text: str) -> dict | None:
    """Return {"verdict": "positive"|"negative", "note": ...} for short feedback.

    Long utterances are never hijacked: they may contain a correction plus a
    real new request, which must reach the agent.
    """
    flat = _flat(text)
    if not flat:
        return None
    tokens = flat.split()
    if len(tokens) > 12:
        return None
    for phrase in _PRAISE:
        if flat == phrase or flat.startswith(phrase + " ") or flat.endswith(" " + phrase):
            note = flat[len(phrase):].strip(" ,.")
            return {"verdict": "positive", "note": note[:200]}
    for phrase in _CORRECTION:
        if flat == phrase or flat.startswith(phrase + " ") or flat.endswith(" " + phrase):
            note = flat[len(phrase):].strip(" ,.")
            note = re.sub(r"^(raje|namesto tega|drugic)\s+", "", note)
            return {"verdict": "negative", "note": note[:200]}
    return None


def detect_remember(text: str) -> dict | None:
    flat = _flat(text)
    if not flat or len(flat.split()) > 14:
        return None
    for phrase in _REMEMBER:
        if phrase in flat:
            note = flat.replace(phrase, " ").strip(" ,.")
            return {"remember": True, "note": note[:200]}
    return None


def detect_intent(text: str) -> str:
    """Coarse intent used for habit sequences and recipe keys."""
    tokens = set(normalize(text))
    groups = (
        ("music", {"glasba", "glasbo", "glazba", "muzika", "pesem", "predvajaj",
                   "zaigraj", "youtube", "spotify", "play", "song", "music"}),
        ("volume", {"glasnost", "glasneje", "tise", "utisaj", "volume", "mute",
                    "louder", "quieter"}),
        ("open", {"odpri", "open", "zazeni", "launch", "pokazi", "show"}),
        ("close", {"zapri", "close", "ustavi", "ugasni", "prekini", "stop"}),
        ("search", {"poisci", "najdi", "search", "google", "preveri", "find"}),
        ("file", {"datoteka", "mapa", "file", "folder", "preberi", "shrani"}),
        ("system", {"sistem", "cpu", "ram", "disk", "proces", "servis", "naprava",
                    "system", "process", "service"}),
        ("screen", {"zaslon", "screenshot", "posnetek", "hud", "panel", "screen"}),
        ("desktop", {"okno", "window", "namizje", "app", "aplikacija", "desktop"}),
        ("task", {"naloga", "opomnik", "kanban", "opomni", "cron", "task",
                  "remind", "reminder"}),
    )
    for name, words in groups:
        if tokens & words:
            return name
    return "chat"


_URL_RE = re.compile(r"https?://([^/\s]+)", re.I)


def extract_entities(text: str) -> list[dict]:
    """Best-effort structured entities for habit mining."""
    entities: list[dict] = []
    for match in _URL_RE.finditer(text or ""):
        entities.append({"kind": "domain", "value": match.group(1).lower()})
    flat = _flat(text)
    m = re.search(r"(?:pusti(?: mi)?|zaigraj|predvajaj)\s+(.+)", flat)
    if m and "pri miru" not in flat and "na miru" not in flat:
        entities.append({"kind": "artist", "value": m.group(1)[:80]})
    m = re.search(r"(?:poisci|najdi|search|preveri)\s+(.+?)(?:\s+(?:in|ter|pa)\s+|$)", flat)
    if m:
        entities.append({"kind": "query", "value": m.group(1)[:80]})
    generic = {"okno", "to", "stran", "zavihek", "tab", "window", "app",
               "aplikacijo", "vse", "glasbo", "glasba", "muziko"}
    for pattern, kind in (
        (r"^(?:odpri|zazeni|launch|open)\s+(.+)$", "app"),
        (r"^(?:zapri|close)\s+(.+)$", "app"),
        (r"^(?:poisci|najdi|search|preveri)\s+(.+)$", "query"),
        (r"^(?:pokazi|show)\s+(.+)$", "query"),
    ):
        match = re.match(pattern, flat)
        if match:
            value = re.split(r"\s+(?:in|ter|pa)\s+", match.group(1).strip(), maxsplit=1)[0]
            value = re.sub(r"^(?:mi|prosim|mi prosim)\s+", "", value).strip()
            if value and not value.startswith("http") and value.lower() not in generic:
                entities.append({"kind": kind, "value": value[:80]})
            break
    return entities


def outcome_from_turn(response: str, errors: list[str] | None = None,
                      interrupted: bool = False) -> str:
    errors = errors or []
    hard = [e for e in errors if not str(e).startswith("ignored:")]
    if interrupted:
        return "partial"
    if hard and not response:
        return "failure"
    if response:
        return "success" if not hard else "partial"
    return "unknown"


def episode_payload(timing: Any, conversation: str, transcript: str,
                    source: str = "voice", response: str | None = None,
                    tools: list[str] | None = None,
                    extra_meta: dict | None = None) -> dict:
    def get(name: str, default: Any = None) -> Any:
        if isinstance(timing, dict):
            return timing.get(name, default)
        return getattr(timing, name, default)

    errors = list(get("errors", []) or [])
    response = response if response is not None else (get("response_text") or "")
    tools = tools if tools is not None else list(get("tools_used", []) or [])
    interrupted = bool(get("interrupted", False))
    duration = None
    summary = get("summary")
    if callable(summary):
        try:
            duration = (summary() or {}).get("total_turn_seconds")
        except Exception:
            duration = None
    if duration is None:
        start = get("end_of_speech_monotonic")
        done = get("total_done_monotonic")
        if start and done:
            duration = round(done - start, 3)
    meta = {"conversation": conversation,
            "entities": extract_entities(transcript),
            "run_id": get("run_id") or "",
            "stt_model": get("stt_model") or "",
            "llm_model": get("llm_model") or "",
            "tts_model": get("tts_model") or ""}
    meta.update(extra_meta or {})
    return {
        "ts": time.time(),
        "session": conversation,
        "source": source,
        "intent": detect_intent(transcript),
        "request": transcript,
        "response": response,
        "tools": tools,
        "steps": [{"tool": t} for t in tools],
        "outcome": outcome_from_turn(response, errors, interrupted),
        "error": "; ".join(str(e) for e in errors if not str(e).startswith("ignored:"))[:1000],
        "duration_s": duration,
        "interrupted": interrupted,
        "tags": [source, detect_intent(transcript)],
        "meta": meta,
    }
