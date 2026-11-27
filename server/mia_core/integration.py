"""Pure helpers that connect the voice/chat loop to the learning core.

Kept free of FastAPI, torch and network imports so it can be tested anywhere.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from .recipes import normalize


def _flat(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9čćžšđ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fold(text: str) -> str:
    """Lowercase + strip diacritics, keeping prepositions (normalize drops them)."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
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


_GOOGLE_SHOW = ("prikazi", "prikaži", "pokazi", "pokaži", "odpri", "show",
                "display", "v brskalniku", "na zaslonu", "brskalnik")
_GOOGLE_ANSWER = ("povej", "odgovori", "razlozi", "razloži", "koliko", "kaj",
                  "kdo", "kdaj", "kje", "zakaj", "kako", "what", "who", "when",
                  "where", "why", "how", "tell")
_GOOGLE_CLEAN = (
    "na googlu", "v googlu", "google", "googlu", "poisci", "poišči", "najdi",
    "search", "in", "ter", "pa", "mi", "prosim", "povej", "odgovori",
    "razlozi", "razloži", "prikazi", "prikaži", "pokazi", "pokaži", "odpri",
    "v brskalniku", "na zaslonu", "brskalnik", "splet", "web", "na", "v",
)


def google_request(text: str) -> tuple[str | None, str]:
    """Split Google requests into 'answer' (background) and 'show' (browser).

    Returns (mode, query) where mode is "answer" or "show"; (None, "") when the
    utterance is not a Google request.
    """
    flat = _flat(text)
    if "google" not in flat and "googlu" not in flat:
        return None, ""
    show = any(word in flat for word in _GOOGLE_SHOW)
    mode = "show" if show else "answer"
    query = flat
    for phrase in sorted(_GOOGLE_CLEAN, key=len, reverse=True):
        query = re.sub(rf"\b{re.escape(phrase)}\b", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    if not query:
        # "odpri google" / just "google": open the Google home page, not a
        # search for the command word itself.
        return "show", ""
    return mode, query


def google_url(query: str) -> str:
    import urllib.parse
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)


_MUSIC_WORDS = ("glazb", "muzik", "glasb", "pesem", "pesm", "predvajaj",
                "zaigraj", "song", "music", "play", "youtube", "jutub", "yt")
_MUSIC_JUNK = (
    "v ozadju", "iz ozadja", "enega od izvajalcev", "od izvajalca",
    "izvajalcev", "izvajalca", "in ga predvajaj", "ter ga predvajaj",
    "in jo predvajaj", "ter jo predvajaj", "predvajaj", "glazbo", "glasbo",
    "muziko", "muzika", "glasba", "glazba", "pesem", "pesmo", "nekaj",
    "neko", "eno", "malce", "prosim", "spet", "ponovno", "kakšno",
    "kaksno", "na youtube", "na youtubu", "na jutubu", "na yt", "youtube",
    "youtubu", "jutub", "jutubu", "yt", "mi",
)


def music_play_request(text: str, fav_match=None) -> str | None:
    """Return the search query, '' for a favourite, or None if not music.

    Understands the natural forms the user actually says:
      »na youtube pusti muziko«, »pusti mi glasbo na youtubu«,
      »youtube predvajaj Bajago«, »poišči na youtube …«.
    """
    flat = _flat(text)
    if not flat:
        return None
    has_music = any(word in flat for word in _MUSIC_WORDS)
    if not has_music:
        match = re.match(r"^pusti(?:te)?(?:\s+mi)?\s+(.+)$", flat)
        if match and fav_match:
            return fav_match(re.sub(r"\s+", " ", match.group(1)).strip())
        return None

    patterns = (
        # »zamenjaj/spremeni/daj glasbo« = another track, not a new search
        r"^(?:zamenjaj|spremeni|menjaj|daj|drugo|druga|novo|nova|naslednjo|naslednja)"
        r"\s+(?:glasbo|muziko|glazbo|pesem|pesmi|predvajanje)\s*(.*)$",
        r"^(?:na\s+)?(?:youtube|jutub|yt)\s+(?:mi\s+)?(?:pusti|predvajaj|zaigraj|poisci|poišči|najdi)\s+(.*)$",
        r"^(?:pusti|pustite|predvajaj|predvajajte|zaigraj|zaigrajte)(?:\s+mi)?\s+(?:na\s+)?(?:youtube|jutub|yt)\s*(.*)$",
        r"^(?:poisci|poišči|najdi|nadi|pronađi|pronadi)\s+(?:na\s+)?(?:youtube|jutub|yt)\s+(.*)$",
        r"^(?:poisci|poišči|najdi|nadi|pronađi|pronadi)\s+(.*)$",
        r"^(?:pusti|pustite|predvajaj|predvajajte|zaigraj|zaigrajte)(?:\s+mi)?\s+(.*)$",
    )
    query = ""
    matched = False
    for pattern in patterns:
        match = re.match(pattern, flat)
        if match:
            query = match.group(1)
            matched = True
            break
    if not matched:
        # A music word alone is not a play command: »ustavi youtube« and
        # »zapri vsa okna youtube« must fall through, not start a new song.
        return None
    query = re.sub(r"^(?:pusti(?:te)?|predvajaj(?:te)?|zaigraj(?:te)?|play)\s+",
                   "", query.strip())
    for junk in _MUSIC_JUNK:
        query = query.replace(junk, " ")
    query = re.sub(r"^od\s+", "", query.strip())
    return re.sub(r"\s+", " ", query).strip()


_STOP_VERBS = frozenset({
    "ustavi", "ustavite", "zaustavi", "zaustavite", "prekini", "prekinite",
    "nehaj", "nehajte", "neham", "nehamo", "koncaj", "koncajte", "ugasni",
    "ugasnite", "utisaj", "utisajte", "stop", "dovolj", "zapri", "zaprite",
    "close",
})
_SHORT_STOP = frozenset({
    "ustavi", "ustavite", "zaustavi", "zaustavite", "prekini", "prekinite",
    "nehaj", "nehajte", "neham", "koncaj", "koncajte", "ugasni", "ugasnite",
    "utisaj", "utisajte", "stop", "dovolj",
})
_STOP_MEDIA = ("glasb", "muzik", "glazb", "pesem", "pesmi", "pesmo",
               "predvaja", "youtube", "jutub", "radio", "video", "film",
               "panel", "music", "song", "playback", " yt ")
_STOP_PHRASES = ("pocisti zaslon", "umakni z zaslona", "ugasni panel",
                 "clear screen")


def media_stop_request(text: str) -> bool:
    """True for »ustavi youtube«, »zapri vsa okna youtube«, »dovolj glasbe«.

    Checked before the music parser and before the command router: those
    phrases contain a music word but are the opposite of a play request, and
    »ugasni glasbo« must never reach the power-shutdown rule.
    """
    flat = _fold(text)
    if not flat:
        return False
    if any(phrase in flat for phrase in _STOP_PHRASES):
        return True
    words = flat.split()
    if len(words) == 1 and words[0] in _SHORT_STOP:
        return True
    if not any(word in _STOP_VERBS for word in words[:3]):
        return False
    padded = f" {flat} "
    if any(target in padded for target in _STOP_MEDIA):
        return True
    # »zapri vsa okna« is media control only with a media word in the sentence
    if "okn" in flat and any(w in words for w in ("vsa", "vse", "oba", "obe")):
        return any(w in flat for w in ("youtube", "jutub", "glasb", "muzik"))
    return False


_WEEKDAYS_SL = ("ponedeljek", "torek", "sreda", "četrtek", "petek",
                "sobota", "nedelja")
_MONTHS_SL = ("januarja", "februarja", "marca", "aprila", "maja", "junija",
              "julija", "avgusta", "septembra", "oktobra", "novembra",
              "decembra")


def time_answer(text: str, now=None) -> str | None:
    """Instant local time/date answer — no LLM, no Hermes session.

    This is deliberately generous: the user should not need an exact phrase
    for something as trivial as the clock.
    """
    import datetime as _dt
    flat = _flat(text)
    if not flat:
        return None
    asks_time = any(phrase in flat for phrase in (
        "koliko je ura", "koliko je uro", "kaj je ura", "kaksna ura",
        "povej mi uro", "povej uro", "ura je", "what time is it",
        "what is the time", "current time",
    ))
    asks_date = any(phrase in flat for phrase in (
        "kateri dan je", "kateri datum", "kaksen dan je", "danes je kateri",
        "kateri dan smo", "what is the date", "what day is it", "todays date",
        "današnji datum", "danasnji datum",
    ))
    if not (asks_time or asks_date):
        return None
    current = now or _dt.datetime.now()
    if asks_time and not asks_date:
        hour, minute = current.hour, current.minute
        if minute == 0:
            return f"Ura je {hour}."
        return f"Ura je {hour} in {minute}."
    if asks_date and not asks_time:
        return (f"Danes je {_WEEKDAYS_SL[current.weekday()]}, "
                f"{current.day}. {_MONTHS_SL[current.month - 1]} {current.year}.")
    return (f"Danes je {_WEEKDAYS_SL[current.weekday()]}, "
            f"{current.day}. {_MONTHS_SL[current.month - 1]} {current.year}, "
            f"ura je {current.hour} in {current.minute}.")


_WEATHER_PHRASES = (
    "kaksno je vreme", "kakvo je vreme", "kako je vreme", "kaksno vreme",
    "vreme v", "vreme za", "vreme na", "napoved", "temperatura",
    "povej mi vreme", "povej vreme", "preveri vreme", "pokazi vreme",
    "prikazi vreme", "bo vreme", "weather",
)
_WEATHER_TIME = {
    "danes", "jutri", "vceraj", "zdaj", "sedaj", "zjutraj", "dopoldne",
    "popoldne", "zvecer", "ponoci", "noc", "jutro", "vikend", "teden",
    "naslednji", "ta", "to", "tem", "vremenu", "vreme", "napoved",
    "temperatura",
}


def weather_request(text: str) -> str | None:
    """Return the spoken city for a weather question ("" = default city).

    Only strong question forms match, so »kaj misliš o vremenu« stays chat.
    """
    flat = _fold(text)
    if not flat:
        return None
    if not any(phrase in flat for phrase in _WEATHER_PHRASES):
        return None
    for city in ("novo mesto", "novem mestu", "nova gorica", "novi gorici",
                 "murska sobota", "murski soboti"):
        if city in flat:
            return city
    match = re.search(
        r"\b(?:v|za|na)\s+(?:kraju\s+)?([a-zčćžšđ][a-zčćžšđ-]{1,30})\b", flat)
    if match:
        city = match.group(1)
        if city not in _WEATHER_TIME:
            return city
    return ""


def hermes_error_text(payload: Any, fallback: str = "") -> str:
    """One actionable sentence for a Hermes ``run.failed``/``error`` event.

    Hermes reports a failed run as the whole run object. When it could not
    resolve a model at all, ``runtime.provider`` and ``runtime.model`` are
    empty — dumping that JSON into the HUD tells the user nothing.
    """
    data = payload if isinstance(payload, dict) else {}
    err = data.get("error")
    if isinstance(err, dict):
        message = str(err.get("message") or err.get("detail") or "").strip()
    else:
        message = str(err or "").strip()
    if message:
        return message[:300]
    runtime = data.get("runtime") or {}
    requested = runtime.get("requested") or {}
    provider = str(runtime.get("provider") or requested.get("provider") or "").strip()
    model = str(runtime.get("model") or requested.get("model") or "").strip()
    if not provider and not model:
        return ("Hermes ni izbral modela (provider in model sta prazna) — preveri, "
                "da llama-server odgovarja na /health in da je model nastavljen "
                "v ~/.hermes.")
    return (fallback or str(data))[:300]


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
            "tts_model": get("tts_model") or "",
            "speaker_stage": get("speaker_stage") or "",
            "speaker_score": get("speaker_score"),
            "speaker_level_db": get("speaker_level_db")}
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
