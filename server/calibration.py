"""Guided distance calibration for the speaker gate.

The HUD drives this over the existing WebSocket: it sends PCM chunks while the
user speaks from a requested distance. This module only holds the state
machine; the server does the TTS prompts and the final embedding work.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16000

DEFAULT_STAGES = [
    {"id": "blizu", "label": "BLIZU mikrofona (0,5 m)", "seconds": 4,
     "samples": 2, "prompt": "Stopi čisto blizu mikrofona in reci: Mia, to je moj glas."},
    {"id": "srednje", "label": "SREDNJE oddaljenosti (2–3 m)", "seconds": 4,
     "samples": 2, "prompt": "Stopi dva do tri metre stran in reci: Mia, ali me slišiš?"},
    {"id": "dalec", "label": "DALEČ (5–6 m)", "seconds": 5,
     "samples": 2, "prompt": "Pojdi čim dlje, pet do šest metrov, in reci: Mia, to je moj glas."},
]


@dataclass
class CalibrationSession:
    stages: list[dict] = field(default_factory=lambda: copy.deepcopy(DEFAULT_STAGES))
    sample_rate: int = SAMPLE_RATE
    index: int = 0
    capture: int = 0
    buffer: bytearray = field(default_factory=bytearray)
    samples: dict[str, list[np.ndarray]] = field(default_factory=dict)
    finished: bool = False
    started: float = field(default_factory=time.time)
    retries: int = 0
    busy: bool = False

    def __post_init__(self) -> None:
        if not self.stages:
            self.stages = copy.deepcopy(DEFAULT_STAGES)
        for stage in self.stages:
            self.samples.setdefault(str(stage["id"]), [])

    @property
    def total_captures(self) -> int:
        return sum(int(s.get("samples", 1)) for s in self.stages)

    @property
    def done_captures(self) -> int:
        return sum(len(v) for v in self.samples.values())

    @property
    def stage(self) -> dict:
        return self.stages[min(self.index, len(self.stages) - 1)]

    def payload(self) -> dict:
        stage = self.stage
        target = int(stage.get("seconds", 4)) * self.sample_rate * 2
        return {
            "active": not self.finished,
            "stage": stage["id"],
            "label": stage.get("label", stage["id"]),
            "prompt": stage.get("prompt", ""),
            "index": self.done_captures + 1,
            "total": self.total_captures,
            "seconds": int(stage.get("seconds", 4)),
            "captured_bytes": len(self.buffer),
            "target_bytes": target,
            "retries": self.retries,
        }

    def add_audio(self, pcm: bytes) -> bool:
        """Append a chunk; return True when the current capture is long enough."""
        if self.finished or self.busy or not pcm:
            return False
        self.buffer.extend(pcm)
        target = int(self.stage.get("seconds", 4)) * self.sample_rate * 2
        return len(self.buffer) >= target

    def take_sample(self) -> np.ndarray:
        sample = np.frombuffer(bytes(self.buffer), dtype=np.int16).copy()
        self.buffer.clear()
        return sample

    def retry_current(self) -> dict:
        self.retries += 1
        self.buffer.clear()
        return {"retry": True, **self.payload()}

    def accept_sample(self, sample: np.ndarray) -> dict:
        if sample.size < int(0.4 * self.sample_rate):
            return self.retry_current()
        stage = self.stage
        self.samples.setdefault(stage["id"], []).append(sample)
        self.capture += 1
        if self.capture >= int(stage.get("samples", 1)):
            self.capture = 0
            self.index += 1
        if self.index >= len(self.stages):
            self.finished = True
            return {"done": True, **self.payload()}
        return {"done": False, **self.payload()}

    def finish(self, gate) -> dict:
        if not any(self.samples.values()):
            raise ValueError("no calibration samples")
        path = gate.enroll_distance(self.samples, append=False)
        status = gate.status()
        return {"path": str(path), "status": status,
                "samples": {k: len(v) for k, v in self.samples.items()},
                "seconds": round(time.time() - self.started, 1)}
