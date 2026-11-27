"""Wake-word addressing and adaptive endpointing (pure numpy)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from continuous import (  # noqa: E402
    FRAME_SAMPLES, SegmenterConfig, UtteranceSegmenter, WakeGate,
    starts_with_exact_wake,
)
from mia_core.integration import media_stop_request  # noqa: E402


class _FakeDetector:
    """Deterministic VAD: 1.0 for speech frames, 0.0 for silence."""

    def __init__(self):
        self.speech = True

    def process(self, frame):
        return 1.0 if self.speech else 0.0

    def loud(self, frame):
        return False


def _frames(count: int, value: int = 1000) -> bytes:
    return np.full(FRAME_SAMPLES * count, value, dtype=np.int16).tobytes()


class WakeAddressTests(unittest.TestCase):
    def test_english_greeting(self):
        self.assertTrue(starts_with_exact_wake("Hey Mia, what is the weather?"))
        self.assertTrue(starts_with_exact_wake("OK Mia, open the browser"))
        self.assertFalse(starts_with_exact_wake("The name Mia is nice"))

    def test_strip_greeting(self):
        gate = WakeGate(["mia"], strict=True)
        self.assertEqual(gate._strip_wake("Hey Mia, open Google"), "open Google")
        self.assertEqual(gate._strip_wake("Mia, odpri Google"), "odpri Google")

    def test_strip_precomposed_accent(self):
        gate = WakeGate(["mia"], strict=True)
        # NFKD expands ì; slicing by a folded offset must still be correct
        self.assertEqual(gate._strip_wake("Mìa, odpri Google"), "odpri Google")

    def test_check_accepts_greeting(self):
        gate = WakeGate(["mia"], strict=True)
        ok, stripped = gate.check("Hello Mia, play music", None, 0.0)
        self.assertTrue(ok)
        self.assertEqual(stripped, "play music")

    def test_wake_word_is_stripped_before_media_stop(self):
        gate = WakeGate(["mia"], strict=True)
        ok, stripped = gate.check("Mia, ustavi", None, 0.0)
        self.assertTrue(ok)
        self.assertTrue(media_stop_request(stripped))
        ok, stripped = gate.check("Mia, zapri vsa okna youtube", None, 0.0)
        self.assertTrue(ok)
        self.assertTrue(media_stop_request(stripped))


class AdaptiveEndpointTests(unittest.TestCase):
    def _segmenter(self):
        cfg = SegmenterConfig(silence_ms=700, min_speech_ms=300,
                              speech_start_ms=96, adaptive_endpoint=True,
                              min_silence_ms=350, max_silence_ms=1100,
                              energy_override=False)
        detector = _FakeDetector()
        return UtteranceSegmenter(detector, cfg), detector

    def _run(self, speech_frames: int, silence_frames: int):
        seg, det = self._segmenter()
        det.speech = True
        events = seg.feed(_frames(speech_frames))
        det.speech = False
        events += seg.feed(_frames(silence_frames))
        return [e for e in events if e[0] == "utterance"]

    def test_short_command_closes_faster(self):
        # ~0.7 s of speech: endpoint ~= 350 ms (11 frames), so 12 frames close it
        self.assertTrue(self._run(22, 12))

    def test_long_sentence_keeps_the_base_pause(self):
        # ~6 s of speech: endpoint ~= 700 ms (22 frames), 12 frames must not close
        self.assertFalse(self._run(190, 12))
        self.assertTrue(self._run(190, 24))

    def test_fixed_endpoint_when_disabled(self):
        cfg = SegmenterConfig(silence_ms=700, min_speech_ms=300,
                              speech_start_ms=96, adaptive_endpoint=False,
                              energy_override=False)
        det = _FakeDetector()
        seg = UtteranceSegmenter(det, cfg)
        det.speech = True
        seg.feed(_frames(22))
        det.speech = False
        events = seg.feed(_frames(12))
        self.assertFalse([e for e in events if e[0] == "utterance"])


if __name__ == "__main__":
    unittest.main()
