"""Speaker verification gate — Mia reacts only to the enrolled voice.

ECAPA-TDNN embeddings (SpeechBrain, CPU) + cosine similarity against a
profile built at enrollment. The gate is fail-open: without a profile file
everything passes, so Mia keeps working until the user calibrates her with
`scripts/enroll_voice.py`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

DEFAULT_MODEL = "speechbrain/spkrec-ecapa-voxceleb"


class SpeakerGate:
    def __init__(self, profile_path: str | Path, threshold: float = 0.30,
                 min_seconds: float = 1.0, model: str = DEFAULT_MODEL):
        self.profile_path = Path(profile_path)
        self.threshold = float(threshold)
        self.min_seconds = float(min_seconds)
        self.model_name = model
        self._embedder = None
        self._profile: np.ndarray | None = None

    @property
    def enrolled(self) -> bool:
        return self.profile_path.exists()

    def _load_model(self):
        if self._embedder is None:
            from speechbrain.inference.speaker import EncoderClassifier
            self._embedder = EncoderClassifier.from_hparams(
                source=self.model_name, run_opts={"device": "cpu"})
        return self._embedder

    def _load_profile(self) -> np.ndarray | None:
        if self._profile is None and self.enrolled:
            self._profile = np.load(self.profile_path)["embedding"]
        return self._profile

    def embed(self, pcm_int16: np.ndarray) -> np.ndarray:
        """L2-normalized speaker embedding for 16 kHz mono int16 audio."""
        import torch
        model = self._load_model()
        wav = torch.from_numpy(pcm_int16.astype(np.float32) / 32768.0).unsqueeze(0)
        with torch.no_grad():
            emb = model.encode_batch(wav).squeeze().cpu().numpy()
        return emb / (np.linalg.norm(emb) + 1e-9)

    def score(self, pcm_int16: np.ndarray) -> float:
        profile = self._load_profile()
        if profile is None:
            return 1.0
        return float(np.dot(self.embed(pcm_int16), profile))

    def verify(self, pcm_int16: np.ndarray) -> tuple[bool, float]:
        """(accept, score). Fail-open: no profile or too-short audio passes —
        short commands stay usable, the wake word still applies."""
        if not self.enrolled:
            return True, 1.0
        if pcm_int16.size < int(self.min_seconds * 16000):
            return True, -1.0
        s = self.score(pcm_int16)
        return s >= self.threshold, s

    def enroll(self, samples: list[np.ndarray]) -> Path:
        """Build the profile from enrolment samples (16 kHz mono int16)."""
        if not samples:
            raise ValueError("no enrolment samples")
        embs = np.stack([self.embed(s) for s in samples])
        mean = embs.mean(axis=0)
        mean /= (np.linalg.norm(mean) + 1e-9)
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.profile_path, embedding=mean)
        self._profile = mean
        return self.profile_path
