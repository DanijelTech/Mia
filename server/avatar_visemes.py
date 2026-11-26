"""Slovenian/English text → Oculus viseme timeline for the 3D avatar.

The TTS backends stream 16 kHz PCM and do not expose phoneme timings. For a
sentence we therefore build a deterministic viseme sequence from the written
form (Slovenian is largely phonemic) and scale it to the *actual* PCM duration.
That keeps the mouth locked to the audio without a second ASR pass. The output
is the Oculus 15-viseme set understood by Ready Player Me / TalkingHead models.
"""

from __future__ import annotations

import re
import unicodedata

VISEMES = ("sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR",
           "aa", "E", "I", "O", "U")

MOOD_WORDS = {
    "warm": ("drago", "lep", "prosim", "hvala", "dobro", "super", "krasno",
             "vesela", "toplo", "sefe", "ljubo"),
    "happy": ("odlicno", "bravo", "super", "vesela", "nasmeh", "zmaga",
              "cestitke", "krasno", "yay"),
    "sad": ("zalostno", "skoda", "žal", "žalostno", "napaka", "ni uspelo",
            "oprosti", "žal mi je"),
    "angry": ("jezna", "groza", "nedopustno", "ne morem", "dovolj"),
    "fearful": ("pazljivo", "nevarno", "bojim", "previdno"),
    "disgust": ("gnusno", "ogabno", "fuj"),
    "love": ("ljubim", "srcek", "rada", "ljubezen"),
    "sleep": ("lahko noc", "spanje", "spat", "utrujena"),
}

_TAG = re.compile(r"\[(mood|emotion|gesture|look|pause)\s*:\s*([a-zčćžšđ0-9_. -]+)\]",
                  re.I)
_PUNCT = re.compile(r"[^a-zčćžšđ0-9\s.,!?;:]+")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def strip_tags(text: str) -> tuple[str, dict]:
    """Remove inline avatar tags and return the clean spoken text + metadata."""
    tags: dict = {}
    def repl(match: re.Match) -> str:
        key = match.group(1).lower()
        value = match.group(2).strip().lower()
        if key in ("mood", "emotion"):
            tags["mood"] = value
        elif key == "gesture":
            tags["gesture"] = value
        elif key == "look":
            tags["look"] = value
        elif key == "pause":
            try:
                tags["pause_ms"] = int(float(value))
            except ValueError:
                pass
        return " "
    return re.sub(r"\s+", " ", _TAG.sub(repl, text or "")).strip(), tags


def mood_for(text: str, tags: dict | None = None) -> str:
    if tags and tags.get("mood"):
        mood = tags["mood"]
        aliases = {"veselo": "happy", "žalostno": "sad", "zalostno": "sad",
                   "jezno": "angry", "prestrašeno": "fearful", "toplo": "warm",
                   "nevtralno": "neutral", "spanje": "sleep", "ljubezen": "love"}
        return aliases.get(mood, mood if mood in MOOD_WORDS or mood == "neutral"
                           else "warm")
    flat = _fold(text)
    for mood, words in MOOD_WORDS.items():
        if any(word in flat for word in words):
            return mood
    if "?" in text:
        return "warm"
    return "neutral"


def _viseme_for(ch: str, two: str) -> str:
    if two in ("lj", "nj", "dž", "dz"):
        return "nn"
    if ch in "aeiou":
        return {"a": "aa", "e": "E", "i": "I", "o": "O", "u": "U"}[ch]
    if ch in "pbm":
        return "PP"
    if ch in "fv":
        return "FF"
    if ch in "td":
        return "DD"
    if ch in "kg":
        return "kk"
    if ch in "čćšž":
        return "CH"
    if ch in "szc":
        return "SS"
    if ch in "nl":
        return "nn"
    if ch == "r":
        return "RR"
    if ch == "h":
        return "kk"
    if ch == "j":
        return "I"
    if ch == "đ":
        return "CH"
    return ""


_WEIGHT = {
    "sil": 1.4, "aa": 1.35, "E": 1.25, "I": 1.1, "O": 1.25, "U": 1.15,
    "PP": .8, "FF": .7, "TH": .75, "DD": .65, "kk": .6, "CH": .8,
    "SS": .75, "nn": .7, "RR": .8,
}


def timeline(text: str, duration_ms: float | None = None,
             *, min_ms: int = 300) -> dict:
    """Return {visemes, times, durations, duration_ms} for one sentence."""
    clean, tags = strip_tags(text)
    flat = _PUNCT.sub(" ", _fold(clean))
    items: list[tuple[str, float]] = []
    i = 0
    while i < len(flat):
        ch = flat[i]
        if ch.isspace():
            items.append(("sil", 1.1))
            i += 1
            continue
        if ch in ".!?;:,":
            items.append(("sil", 2.8 if ch in ".!?" else 1.8))
            i += 1
            continue
        two = flat[i:i + 2]
        vis = _viseme_for(ch, two)
        if vis:
            items.append((vis, _WEIGHT.get(vis, 1.0)))
            i += 2 if two in ("lj", "nj", "dž", "dz") else 1
        else:
            i += 1
    if not items:
        items = [("sil", 1.0)]
    total_weight = sum(w for _, w in items) or 1.0
    target = max(min_ms, float(duration_ms or (total_weight * 80)))
    scale = target / total_weight
    visemes: list[str] = []
    times: list[int] = []
    durations: list[int] = []
    t = 0.0
    for vis, weight in items:
        d = weight * scale
        visemes.append(vis)
        times.append(int(round(t)))
        durations.append(max(35, int(round(d))))
        t += d
    return {"visemes": visemes, "times": times, "durations": durations,
            "duration_ms": int(round(t)), "mood": mood_for(clean, tags),
            "gesture": tags.get("gesture") or "", "look": tags.get("look") or ""}


def timeline_for_pcm(text: str, pcm: bytes, sample_rate: int = 16000) -> dict:
    # PCM is mono 16-bit: two bytes per sample.
    duration_ms = len(pcm) / 2 / max(1, sample_rate) * 1000.0
    return timeline(text, duration_ms)
