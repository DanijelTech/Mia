"""Tests for strict wake, distance calibration and Google intent split."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core.integration import google_request, google_url  # noqa: E402

try:
    import numpy as np
    from calibration import CalibrationSession  # noqa: E402
    from continuous import WakeGate  # noqa: E402
    from speaker_gate import SpeakerGate, level_db  # noqa: E402
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class StrictWakeTests(unittest.TestCase):
    def setUp(self):
        self.gate = WakeGate(["mia", "mijo", "mija"], strict=True)

    def test_accepts_explicit_wake(self):
        accept, stripped = self.gate.check("Mia, odpri mi google", None, 1000)
        self.assertTrue(accept)
        self.assertEqual(stripped, "odpri mi google")

    def test_rejects_mid_sentence_mention(self):
        accept, _ = self.gate.check("danes je mia lepa", None, 1000)
        self.assertFalse(accept)

    def test_strict_ignores_followup_window(self):
        gate = WakeGate(["mia"], followup_seconds=20, strict=True)
        accept, _ = gate.check("kaj je novega", last_reply_at=999.0, now=1000.0)
        self.assertFalse(accept)

    def test_non_strict_followup_still_works(self):
        gate = WakeGate(["mia"], followup_seconds=20, strict=False)
        accept, _ = gate.check("kaj je novega", last_reply_at=999.0, now=1000.0)
        self.assertTrue(accept)


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class CalibrationTests(unittest.TestCase):
    def test_level_db(self):
        silence = np.zeros(16000, dtype=np.int16)
        loud = np.full(16000, 16000, dtype=np.int16)
        self.assertLess(level_db(silence), -100)
        self.assertGreater(level_db(loud), -10)

    def test_state_machine(self):
        stages = [
            {"id": "blizu", "label": "near", "seconds": 1, "samples": 1,
             "prompt": "near"},
            {"id": "dalec", "label": "far", "seconds": 1, "samples": 1,
             "prompt": "far"},
        ]
        session = CalibrationSession(stages=stages)
        self.assertEqual(session.total_captures, 2)
        self.assertEqual(session.payload()["stage"], "blizu")
        self.assertFalse(session.add_audio(b"\x00\x00" * 8000))
        self.assertTrue(session.add_audio(b"\x00\x00" * 8000))
        sample = session.take_sample()
        self.assertEqual(sample.size, 16000)
        state = session.accept_sample(sample)
        self.assertFalse(state["done"])
        self.assertEqual(state["stage"], "dalec")
        session.add_audio(b"\x00\x00" * 16000)
        state = session.accept_sample(session.take_sample())
        self.assertTrue(state["done"])
        self.assertEqual(len(session.samples["blizu"]), 1)
        self.assertEqual(len(session.samples["dalec"]), 1)

    def test_gate_status_without_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate = SpeakerGate(Path(tmp) / "missing.npz")
            self.assertFalse(gate.enrolled)
            status = gate.status()
            self.assertFalse(status["enrolled"])
            accept, score = gate.verify(np.zeros(16000, dtype=np.int16))
            self.assertTrue(accept)  # fail-open unless require_profile
            self.assertEqual(score, 1.0)


class GoogleIntentTests(unittest.TestCase):
    def test_answer_vs_show(self):
        self.assertEqual(google_request("na googlu poišči in povej mi vreme"),
                         ("answer", "vreme"))
        self.assertEqual(google_request("prikaži mi v googlu vreme"),
                         ("show", "vreme"))
        self.assertEqual(google_request("pokaži na googlu koliko je ura"),
                         ("show", "koliko je ura"))
        self.assertEqual(google_request("odpri google in poišči vreme"),
                         ("show", "vreme"))
        self.assertEqual(google_request("poišči na googlu vreme"),
                         ("answer", "vreme"))

    def test_non_google(self):
        self.assertEqual(google_request("kaj je danes za kosilo"), (None, ""))

    def test_url(self):
        self.assertIn("google.com/search?q=vreme", google_url("vreme"))


if __name__ == "__main__":
    unittest.main()
