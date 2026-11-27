"""Tests for the TTS fallback wrapper (primary HTTP -> Piper)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

try:
    import numpy  # noqa: F401  (tts.py imports numpy at module level)
    import tts
except Exception:  # pragma: no cover - stdlib-only dev container
    tts = None


class _FakeBackend:
    """Minimal TTSBackend stand-in; the fallback logic is the unit under test."""

    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or []
        self.error = error
        self.label = "fake"

    def synth(self, text):
        if self.error is not None:
            raise self.error
        yield from self.chunks


@unittest.skipIf(tts is None, "numpy not installed")
class TTSFallbackTests(unittest.TestCase):
    def test_primary_is_used_when_healthy(self):
        backend = tts.FallbackBackend(
            _FakeBackend([b"a"]), _FakeBackend([b"b"]))
        self.assertEqual(list(backend.synth("x")), [b"a"])

    def test_falls_back_before_any_audio(self):
        backend = tts.FallbackBackend(
            _FakeBackend(error=RuntimeError("down")), _FakeBackend([b"b"]))
        self.assertEqual(list(backend.synth("x")), [b"b"])

    def test_pitch_getter_reaches_the_primary_backend(self):
        primary, fallback = _FakeBackend([b"a"]), _FakeBackend([b"b"])
        backend = tts.FallbackBackend(primary, fallback)
        backend.pitch_getter = lambda: 4.0
        self.assertEqual(primary.pitch_getter(), 4.0)
        self.assertEqual(fallback.pitch_getter(), 4.0)

    def test_does_not_switch_after_audio_started(self):
        class Partial(_FakeBackend):
            def synth(self, text):
                yield b"a"
                raise RuntimeError("late")

        backend = tts.FallbackBackend(Partial(), _FakeBackend([b"b"]))
        with self.assertRaises(RuntimeError):
            list(backend.synth("x"))


if __name__ == "__main__":
    unittest.main()
