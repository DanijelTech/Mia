"""Always-listening segmentation for the Mia voice server.

In continuous mode the HUD sends one long PCM stream instead of push-to-talk
start/stop pairs. This module turns that stream into utterances:

    detector   (Silero VAD if torch is available, otherwise RMS energy)
    segmenter  speech/silence state machine, keeps a pre-roll so the first
               syllable is not cut, ignores coughs shorter than min_speech_ms
    wake gate  "Mia, ..." starts a turn; a follow-up window lets you continue
               without repeating the wake word

Everything here is pure Python + numpy so it can be unit-tested without audio.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import numpy as np

FRAME_SAMPLES = 512          # 32 ms at 16 kHz — what Silero expects
SAMPLE_RATE = 16000
FRAME_MS = FRAME_SAMPLES * 1000 // SAMPLE_RATE


def _ascii(text: str) -> str:
    """Lowercase ASCII fold so 'Mìa', 'MIA,' and 'mia' all match."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def _fold_with_map(text: str) -> tuple[str, list[int]]:
    """ASCII fold plus a folded-index -> original-index map.

    The map matters when the original contains precomposed accented letters
    (NFKD expands them and the combining mark is dropped), so slicing the
    original by a folded offset would cut in the wrong place.
    """
    out: list[str] = []
    index: list[int] = []
    for pos, ch in enumerate(text or ""):
        for part in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(part):
                continue
            for low in part.lower():
                out.append(low)
                index.append(pos)
    return "".join(out), index


# Spoken greetings in front of the wake word: "hey Mia, …", "ok Mia …".
_GREETING_RE = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|yo|hej|ej|oj|zdravo|dober\s+dan|"
    r"dobro\s+jutro|dobro\s+vecer|good\s+morning|good\s+afternoon|"
    r"good\s+evening|hey\s+there)\b[\s,.;:!?-]*)+", re.I)


def starts_with_exact_wake(text: str, word: str = "mia") -> bool:
    """EXACT wake word at the start (no fuzzy variants) — the bar for turns
    whose speaker verification FAILED: Whisper mishearings of noise ('nja',
    'mja') must not trigger overrides. A spoken greeting before the wake word
    is allowed: »Hey Mia …« is the normal English form."""
    flat = _GREETING_RE.sub("", _ascii(text).strip())
    return bool(re.match(rf"{re.escape(word)}(?=[\s,.!?]|$)", flat))


class SpeechDetector:
    """Speech probability for 32 ms frames.

    Silero VAD is used when `torch` and `silero_vad` are importable (the voice
    server has both through RealtimeSTT); otherwise an adaptive RMS energy gate
    keeps continuous mode usable on a CPU-only box.
    """

    def __init__(self, min_rms: float = 320.0, threshold: float = 0.5):
        self.min_rms = float(min_rms)
        self.threshold = float(threshold)
        self._silero = None
        self._torch = None
        self._noise = 120.0
        self._init_silero()

    def _init_silero(self) -> None:
        try:
            import torch  # noqa: PLC0415
            from silero_vad import load_silero_vad  # noqa: PLC0415
        except Exception:
            return
        try:
            self._torch = torch
            self._silero = load_silero_vad()
            self._silero.eval()
        except Exception:
            self._silero = None

    @property
    def kind(self) -> str:
        return "silero" if self._silero is not None else "rms"

    def loud(self, frame: np.ndarray) -> bool:
        """Energy gate: is this frame clearly above the room noise floor?"""
        if frame.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))))
        if rms < self._noise * 1.5:
            self._noise = 0.98 * self._noise + 0.02 * rms
        return rms >= max(self.min_rms, self._noise * 3.0)

    def process(self, frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        if self._silero is not None:
            try:
                with self._torch.no_grad():
                    tensor = self._torch.from_numpy(frame.astype(np.float32) / 32768.0)
                    return float(self._silero(tensor, SAMPLE_RATE).item())
            except Exception:
                self._silero = None          # fall back for the rest of the session
        return 1.0 if self.loud(frame) else 0.0


@dataclass
class SegmenterConfig:
    silence_ms: int = 700
    min_speech_ms: int = 300
    pre_roll_ms: int = 320
    threshold: float = 0.4          # to start an utterance
    end_threshold: float = 0.25     # to keep it open (hysteresis)
    max_utterance_ms: int = 20000   # never swallow speech: force-close here
    energy_override: bool = True    # loud audio counts as speech even if VAD says no
    speech_start_ms: int = 96       # consecutive speech before "speech_start" fires (click/noise debounce)
    adaptive_endpoint: bool = True  # shorter pauses for short commands
    min_silence_ms: int = 350
    max_silence_ms: int = 1100


class UtteranceSegmenter:
    """Feed PCM, get ('speech_start'|'utterance', payload) events."""

    def __init__(self, detector: SpeechDetector, cfg: SegmenterConfig | None = None):
        self.cfg = cfg or SegmenterConfig()
        self.detector = detector
        self._max_frames = max(1, self.cfg.max_utterance_ms // FRAME_MS)
        self._min_speech_frames = max(1, self.cfg.min_speech_ms // FRAME_MS)
        self._pre_roll_frames = max(1, self.cfg.pre_roll_ms // FRAME_MS)
        self._start_frames = max(1, self.cfg.speech_start_ms // FRAME_MS)
        self._pending = b""
        self.reset()

    def _endpoint_frames(self) -> int:
        """Adaptive endpointing: a short command closes faster than a long one.

        The base ``silence_ms`` is the ceiling; short utterances scale it down
        to ``min_silence_ms``. This trims 200–350 ms from typical commands
        without cutting off slower, thoughtful sentences.
        """
        base = max(120, int(self.cfg.silence_ms))
        if not self.cfg.adaptive_endpoint:
            return max(1, base // FRAME_MS)
        speech_ms = self._speech_frames * FRAME_MS
        factor = 0.45 + 0.55 * min(1.0, speech_ms / 5000.0)
        target = int(base * factor)
        target = max(int(self.cfg.min_silence_ms), min(int(self.cfg.max_silence_ms), target))
        return max(1, target // FRAME_MS)

    def reset(self) -> None:
        self._pre: list[bytes] = []
        self._buf = bytearray()
        self._speaking = False
        self._silence_run = 0
        self._speech_frames = 0
        self._announced = False
        self._onset_run = 0
        self.state = "silence"
        self.prob = 0.0

    def feed(self, pcm: bytes) -> list[tuple[str, bytes]]:
        events: list[tuple[str, bytes]] = []
        data = self._pending + pcm if self._pending else pcm
        frame_bytes = FRAME_SAMPLES * 2
        usable = len(data) - (len(data) % frame_bytes)
        self._pending = data[usable:]
        for off in range(0, usable, frame_bytes):
            frame = np.frombuffer(data[off:off + frame_bytes], dtype=np.int16)
            prob = self.detector.process(frame)
            loud = bool(self.cfg.energy_override and hasattr(self.detector, "loud")
                        and self.detector.loud(frame))
            threshold = self.cfg.end_threshold if self._speaking else self.cfg.threshold
            # In speech the lower end-threshold (hysteresis) keeps the
            # utterance open through short gaps; loud audio always counts.
            is_speech = prob >= threshold or loud
            self.prob = float(prob)
            self.state = "speech" if self._speaking else "silence"

            if not self._speaking:
                self._pre.append(data[off:off + frame_bytes])
                if len(self._pre) > self._pre_roll_frames:
                    self._pre.pop(0)
                if is_speech:
                    self._onset_run += 1
                    if self._onset_run >= self._start_frames:
                        self._speaking = True
                        self._silence_run = 0
                        self._speech_frames = self._onset_run
                        self._buf = bytearray(b"".join(self._pre))
                        if not self._announced:
                            self._announced = True
                            events.append(("speech_start", b""))
                else:
                    self._onset_run = 0
                continue

            self._buf.extend(data[off:off + frame_bytes])
            forced = self._speech_frames >= self._max_frames
            if is_speech and not forced:
                self._silence_run = 0
                self._speech_frames += 1
            else:
                self._silence_run += 1
                if forced or self._silence_run >= self._endpoint_frames():
                    payload = bytes(self._buf)
                    self._speaking = False
                    self._announced = False
                    self._buf = bytearray()
                    self._pre = []
                    self._silence_run = 0
                    self._onset_run = 0
                    if self._speech_frames >= self._min_speech_frames:
                        events.append(("utterance", payload))
                    self._speech_frames = 0
        return events

    def flush(self) -> list[tuple[str, bytes]]:
        """End of stream: hand back whatever was being spoken."""
        events: list[tuple[str, bytes]] = []
        if self._speaking and self._speech_frames >= self._min_speech_frames:
            events.append(("utterance", bytes(self._buf)))
        self.reset()
        return events


class WakeGate:
    """Require 'Mia' to start every turn.

    `strict=True` removes the follow-up window entirely: even a sentence said
    two seconds after Mia's reply must start with the wake word. This is the
    production default for a house with TVs, guests and noise.
    """

    def __init__(self, words: list[str] | None = None, followup_seconds: float = 20.0,
                 strict: bool = False):
        self.words = [_ascii(w).strip() for w in (words or []) if str(w).strip()]
        self.followup = float(followup_seconds)
        self.strict = bool(strict)

    def _strip_wake(self, text: str) -> str:
        folded, index = _fold_with_map(text)
        # A greeting in front of the wake word ("hey Mia, …") is part of the
        # address, not the request; drop it together with the wake word.
        greeting = _GREETING_RE.match(folded)
        start = greeting.end() if greeting else 0
        view = folded[start:]
        for word in sorted(self.words, key=len, reverse=True):
            # the lookahead keeps the wake word on a word boundary: "miara"
            # must not become "ra", and a bare "Mia" must become ""
            m = re.match(rf"^[\s,.;:!?-]*{re.escape(word)}(?=[\s,.;:!?-]|$)(.*)$",
                         view, re.S)
            if m:
                end_folded = len(folded) - len(m.group(1))
                cut = index[end_folded] if end_folded < len(index) else len(text)
                return text[cut:].lstrip(" ,.;:!?-")
        return text

    def starts_with_wake(self, text: str) -> bool:
        """Strict check: the utterance STARTS with a wake word (no followup
        window) — used for the speaker-gate override while music plays."""
        flat = _GREETING_RE.sub("", _ascii(text).strip())
        return any(re.match(rf"{re.escape(w)}(?=[\s,.;:!?-]|$)", flat) for w in self.words)

    def check(self, transcript: str, last_reply_at: float | None, now: float) -> tuple[bool, str]:
        if not self.words:
            return True, transcript
        # The wake word must be the FIRST word: a sentence that merely mentions
        # "Mia" later on ("danes je mia lepa", TV dialogue) must not start a
        # turn. Set `followup_seconds: 0` to require it on every single turn.
        if self.starts_with_wake(transcript):
            return True, self._strip_wake(transcript)
        if self.strict:
            return False, transcript
        if (self.followup > 0 and last_reply_at is not None
                and (now - last_reply_at) <= self.followup):
            return True, transcript
        return False, transcript


def build_segmenter(cfg: dict | None, detector: SpeechDetector | None = None) -> UtteranceSegmenter:
    c = (cfg or {})
    return UtteranceSegmenter(
        detector or SpeechDetector(min_rms=float(c.get("min_rms", 320))),
        SegmenterConfig(
            silence_ms=int(c.get("silence_ms", 700)),
            min_speech_ms=int(c.get("min_speech_ms", 300)),
            pre_roll_ms=int(c.get("pre_roll_ms", 320)),
            threshold=float(c.get("threshold", 0.4)),
            end_threshold=float(c.get("end_threshold", 0.25)),
            max_utterance_ms=int(c.get("max_utterance_ms", 20000)),
            energy_override=bool(c.get("energy_override", True)),
            speech_start_ms=int(c.get("speech_start_ms", 96)),
            adaptive_endpoint=bool(c.get("adaptive_endpoint", True)),
            min_silence_ms=int(c.get("min_silence_ms", 350)),
            max_silence_ms=int(c.get("max_silence_ms", 1100)),
        ),
    )
