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
        # reload on mtime change: re-enrollment happens in a separate process
        try:
            mtime = self.profile_path.stat().st_mtime
        except OSError:
            return None
        if self._profile is None or mtime != getattr(self, "_profile_mtime", None):
            self._profile = np.load(self.profile_path)["embedding"]
            self._profile_mtime = mtime
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
        """(accept, score). Without a profile everything passes (fail-open).

        With a profile, short clips are judged instead of waved through: the
        old fail-open for anything under `min_seconds` let every cough, door
        slam and TV burst reach the transcriber. ECAPA is usable from ~0.5 s,
        so below `min_seconds` a slightly stricter threshold applies; clips
        under 0.4 s carry too little signal and are rejected outright.
        """
        if not self.enrolled:
            return True, 1.0
        if pcm_int16.size < int(0.4 * 16000):
            return False, -1.0
        s = self.score(pcm_int16)
        short = pcm_int16.size < int(self.min_seconds * 16000)
        return s >= self.threshold + (0.05 if short else 0.0), s

    def enroll(self, samples: list[np.ndarray], append: bool = False) -> Path:
        """Build the profile from enrolment samples (16 kHz mono int16).

        append=True merges with the existing profile (e.g. adding another
        language): the profile is the mean of ALL samples ever enrolled.
        """
        if not samples:
            raise ValueError("no enrolment samples")
        embs = [self.embed(s) for s in samples]
        if append and self.enrolled:
            data = np.load(self.profile_path)
            if "samples" in data:
                embs = [e for e in data["samples"]] + embs
            else:  # old single-vector profile counts as one sample
                embs = [data["embedding"]] + embs
        stack = np.stack(embs)
        mean = stack.mean(axis=0)
        mean /= (np.linalg.norm(mean) + 1e-9)
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.profile_path, embedding=mean, samples=stack)
        self._profile = mean
        return self.profile_path
