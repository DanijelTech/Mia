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
from dataclasses import dataclass, field

import numpy as np

FRAME_SAMPLES = 512          # 32 ms at 16 kHz — what Silero expects
SAMPLE_RATE = 16000
FRAME_MS = FRAME_SAMPLES * 1000 // SAMPLE_RATE


def _ascii(text: str) -> str:
    """Lowercase ASCII fold so 'Mìa', 'MIA,' and 'mia' all match."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


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


class UtteranceSegmenter:
    """Feed PCM, get ('speech_start'|'utterance', payload) events."""

    def __init__(self, detector: SpeechDetector, cfg: SegmenterConfig | None = None):
        self.cfg = cfg or SegmenterConfig()
        self.detector = detector
        self._silence_frames = max(1, self.cfg.silence_ms // FRAME_MS)
        self._max_frames = max(1, self.cfg.max_utterance_ms // FRAME_MS)
        self._min_speech_frames = max(1, self.cfg.min_speech_ms // FRAME_MS)
        self._pre_roll_frames = max(1, self.cfg.pre_roll_ms // FRAME_MS)
        self._pending = b""
        self.reset()

    def reset(self) -> None:
        self._pre: list[bytes] = []
        self._buf = bytearray()
        self._speaking = False
        self._silence_run = 0
        self._speech_frames = 0
        self._announced = False
        self.state = "silence"
        self.prob = 0.0
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
            if self._speaking:
                # end only when the VAD says silence *and* the room is quiet
                is_speech = prob >= threshold or loud
            else:
                is_speech = prob >= threshold or loud
            self.prob = float(prob)
            self.state = "speech" if self._speaking else "silence"

            if not self._speaking:
                self._pre.append(data[off:off + frame_bytes])
                if len(self._pre) > self._pre_roll_frames:
                    self._pre.pop(0)
                if is_speech:
                    self._speaking = True
                    self._silence_run = 0
                    self._speech_frames = 1
                    self._buf = bytearray(b"".join(self._pre))
                    if not self._announced:
                        self._announced = True
                        events.append(("speech_start", b""))
                continue

            self._buf.extend(data[off:off + frame_bytes])
            forced = self._speech_frames >= self._max_frames
            if is_speech and not forced:
                self._silence_run = 0
                self._speech_frames += 1
            else:
                self._silence_run += 1
                if forced or self._silence_run >= self._silence_frames:
                    payload = bytes(self._buf)
                    self._speaking = False
                    self._announced = False
                    self._buf = bytearray()
                    self._pre = []
                    self._silence_run = 0
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
    """Require 'Mia' to start a conversation, then allow a follow-up window."""

    def __init__(self, words: list[str] | None = None, followup_seconds: float = 20.0):
        self.words = [_ascii(w).strip() for w in (words or []) if str(w).strip()]
        self.followup = float(followup_seconds)

    def _strip_wake(self, text: str) -> str:
        flat = _ascii(text)
        for word in sorted(self.words, key=len, reverse=True):
            m = re.match(rf"^[\s,.;:!?-]*{re.escape(word)}[\s,.;:!?-]*(.*)$", flat, re.S)
            if m:
                # map the ASCII prefix length back onto the original text
                cut = len(text) - len(m.group(1)) if m.group(1) else len(text)
                rest = text[cut:].lstrip(" ,.;:!?-")
                return rest or text
        return text

    def check(self, transcript: str, last_reply_at: float | None, now: float) -> tuple[bool, str]:
        if not self.words:
            return True, transcript
        flat = _ascii(transcript).strip()
        said_wake = any(flat.startswith(w) for w in self.words) or any(
            re.search(rf"(^|\s){re.escape(w)}(\s|$)", flat) for w in self.words
        )
        if said_wake:
            return True, self._strip_wake(transcript)
        if last_reply_at is not None and (now - last_reply_at) <= self.followup:
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
        ),
    )
