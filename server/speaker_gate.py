"""Speaker verification gate — Mia reacts only to the enrolled voice.

The profile is distance-aware: enrolment can capture the same speaker near,
mid-room and far from the microphone. Verification embeds the utterance once
and compares it with every distance centroid; the best match wins. The audio
level is recorded with each centroid so the server can log which distance was
used and, when a far sample is noisier, apply the calibrated (slightly lower)
threshold for that distance.

Fail-open without a profile unless `require_profile=True`. The profile is a
plain NPZ file, reloaded when its mtime changes, so re-calibration needs no
restart.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEFAULT_MODEL = "speechbrain/spkrec-ecapa-voxceleb"
SAMPLE_RATE = 16000


def level_db(pcm_int16: np.ndarray) -> float:
    """RMS level in dBFS (0 dB = full scale, negative = quieter)."""
    if pcm_int16.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(pcm_int16.astype(np.float32)))))
    return round(20.0 * np.log10(max(rms, 1e-9) / 32768.0), 2)


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / (np.linalg.norm(vector) + 1e-9)


@dataclass
class StageProfile:
    name: str
    embedding: np.ndarray
    level_db: float
    level_std: float
    count: int
    threshold: float


class SpeakerGate:
    def __init__(self, profile_path: str | Path, threshold: float = 0.30,
                 min_seconds: float = 1.0, model: str = DEFAULT_MODEL,
                 require_profile: bool = False):
        self.profile_path = Path(profile_path)
        self.threshold = float(threshold)
        self.min_seconds = float(min_seconds)
        self.model_name = model
        self.require_profile = bool(require_profile)
        self._embedder = None
        self._profile: dict | None = None
        self._profile_mtime: float | None = None

    # ------------------------------------------------------------- profile
    @property
    def enrolled(self) -> bool:
        return self.profile_path.exists()

    def _load_model(self):
        if self._embedder is None:
            from speechbrain.inference.speaker import EncoderClassifier
            self._embedder = EncoderClassifier.from_hparams(
                source=self.model_name, run_opts={"device": "cpu"})
        return self._embedder

    def _load_profile(self) -> dict | None:
        try:
            mtime = self.profile_path.stat().st_mtime
        except OSError:
            return None
        if self._profile is not None and mtime == self._profile_mtime:
            return self._profile
        data = np.load(self.profile_path, allow_pickle=False)
        embedding = _unit(np.asarray(data["embedding"], dtype=np.float32))
        samples = np.asarray(data["samples"], dtype=np.float32) if "samples" in data else None
        names = [str(x) for x in data["stage_names"]] if "stage_names" in data else ["default"]
        stage_embeddings = (np.asarray(data["stage_embeddings"], dtype=np.float32)
                            if "stage_embeddings" in data else embedding[None, :])
        levels = (np.asarray(data["stage_levels"], dtype=np.float32)
                  if "stage_levels" in data else np.array([0.0], dtype=np.float32))
        level_stds = (np.asarray(data["stage_level_stds"], dtype=np.float32)
                      if "stage_level_stds" in data else np.zeros(len(names), dtype=np.float32))
        counts = (np.asarray(data["stage_counts"], dtype=np.int32)
                  if "stage_counts" in data else np.array([1], dtype=np.int32))
        thresholds = (np.asarray(data["stage_thresholds"], dtype=np.float32)
                      if "stage_thresholds" in data else np.full(len(names), self.threshold))
        self._profile = {
            "embedding": embedding,
            "samples": samples,
            "stages": [StageProfile(str(names[i]), _unit(stage_embeddings[i]),
                                    float(levels[i]), float(level_stds[i]),
                                    int(counts[i]), float(thresholds[i]))
                       for i in range(len(names))],
        }
        self._profile_mtime = mtime
        return self._profile

    @property
    def distance_enrolled(self) -> bool:
        profile = self._load_profile()
        return bool(profile and len(profile["stages"]) > 1)

    def status(self) -> dict:
        profile = self._load_profile()
        if not profile:
            return {"enrolled": False, "distance_enrolled": False,
                    "profile": str(self.profile_path), "stages": [],
                    "threshold": self.threshold,
                    "require_profile": self.require_profile}
        return {
            "enrolled": True,
            "distance_enrolled": len(profile["stages"]) > 1,
            "profile": str(self.profile_path),
            "threshold": self.threshold,
            "require_profile": self.require_profile,
            "mtime": self._profile_mtime,
            "stages": [
                {"name": s.name, "count": s.count, "level_db": s.level_db,
                 "level_std": s.level_std, "threshold": s.threshold}
                for s in profile["stages"]
            ],
        }

    # ------------------------------------------------------------- embedding
    def embed(self, pcm_int16: np.ndarray) -> np.ndarray:
        """L2-normalized speaker embedding for 16 kHz mono int16 audio."""
        import torch
        model = self._load_model()
        wav = torch.from_numpy(pcm_int16.astype(np.float32) / 32768.0).unsqueeze(0)
        with torch.no_grad():
            emb = model.encode_batch(wav).squeeze().cpu().numpy()
        return _unit(np.asarray(emb, dtype=np.float32))

    def _stage_threshold(self, stage: StageProfile) -> float:
        # Never let a self-similarity estimate push the live threshold ABOVE
        # the configured base: ECAPA self-scores across different sentences can
        # be high, and that used to reject the user after calibration.
        # Raising the base still works: the stage estimate is lifted with it,
        # but the base remains the hard ceiling.
        shift = max(0.0, self.threshold - 0.30)
        return round(max(0.18, min(self.threshold,
                                   stage.threshold + shift)), 4)

    def verify_detail(self, pcm_int16: np.ndarray) -> dict:
        level = level_db(pcm_int16)
        if not self.enrolled:
            return {"accept": not self.require_profile, "score": 1.0,
                    "overall_score": 1.0, "stage": "none", "level_db": level,
                    "threshold": 0.0, "reason": "no_profile"}
        if pcm_int16.size < int(0.4 * SAMPLE_RATE):
            return {"accept": False, "score": -1.0, "overall_score": -1.0,
                    "stage": "too_short", "level_db": level,
                    "threshold": self.threshold, "reason": "too_short"}
        profile = self._load_profile()
        if not profile:
            return {"accept": not self.require_profile, "score": 1.0,
                    "overall_score": 1.0, "stage": "none", "level_db": level,
                    "threshold": 0.0, "reason": "profile_unreadable"}
        emb = self.embed(pcm_int16)
        overall = float(np.dot(emb, profile["embedding"]))
        scores = [float(np.dot(emb, stage.embedding)) for stage in profile["stages"]]
        best = int(np.argmax(scores)) if scores else 0
        stage = profile["stages"][best]
        threshold = self._stage_threshold(stage)
        short = pcm_int16.size < int(self.min_seconds * SAMPLE_RATE)
        if short:
            threshold += 0.05
        best_score = max(overall, scores[best] if scores else overall)
        accept = best_score >= threshold
        return {"accept": bool(accept), "score": round(best_score, 4),
                "overall_score": round(overall, 4),
                "stage": stage.name, "level_db": level,
                "threshold": round(threshold, 4),
                "reason": "ok" if accept else "below_threshold"}

    def score(self, pcm_int16: np.ndarray) -> float:
        return float(self.verify_detail(pcm_int16)["score"])

    def verify(self, pcm_int16: np.ndarray) -> tuple[bool, float]:
        detail = self.verify_detail(pcm_int16)
        return bool(detail["accept"]), float(detail["score"])

    # ------------------------------------------------------------- enrolment
    def enroll(self, samples: list[np.ndarray], append: bool = False,
               stages: list[str] | None = None) -> Path:
        """Build a profile from samples (16 kHz mono int16).

        `stages` has one label per sample. Without labels all samples form the
        legacy single-stage profile.
        """
        if not samples:
            raise ValueError("no enrolment samples")
        labels = stages or ["default"] * len(samples)
        if len(labels) != len(samples):
            raise ValueError("stages and samples length mismatch")
        grouped: dict[str, list[np.ndarray]] = {}
        for label, sample in zip(labels, samples):
            grouped.setdefault(str(label), []).append(sample)
        return self.enroll_distance(grouped, append=append)

    def enroll_distance(self, samples_by_stage: dict[str, list[np.ndarray]],
                        append: bool = False) -> Path:
        grouped = {str(k): [s for s in v if s.size >= int(0.4 * SAMPLE_RATE)]
                   for k, v in samples_by_stage.items()}
        grouped = {k: v for k, v in grouped.items() if v}
        if not grouped:
            raise ValueError("no usable enrolment samples")
        if append and self.enrolled:
            profile = self._load_profile()
            if profile:
                # merge old raw samples when available, else old centroids
                old = {s.name: [] for s in profile["stages"]}
                if profile.get("samples") is not None:
                    old_samples = profile["samples"]
                    # old profiles without per-sample labels go to "default"
                    if len(profile["stages"]) == 1:
                        old[profile["stages"][0].name] = list(old_samples)
                for name, samples in old.items():
                    if samples:
                        grouped.setdefault(name, []).extend(samples)
        names = sorted(grouped)
        all_embs: list[np.ndarray] = []
        stage_embs: list[np.ndarray] = []
        stage_levels, stage_stds, stage_counts, stage_thresholds = [], [], [], []
        for name in names:
            embs = [self.embed(s) for s in grouped[name]]
            all_embs.extend(embs)
            centroid = _unit(np.stack(embs).mean(axis=0))
            stage_embs.append(centroid)
            levels = [level_db(s) for s in grouped[name]]
            stage_levels.append(float(np.mean(levels)))
            stage_stds.append(float(np.std(levels)))
            stage_counts.append(len(embs))
            self_scores = [float(np.dot(e, centroid)) for e in embs]
            stage_thresholds.append(round(max(0.18,
                                              float(np.mean(self_scores)) - 0.10), 4))
        overall = _unit(np.stack(all_embs).mean(axis=0))
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            self.profile_path,
            embedding=overall,
            samples=np.stack(all_embs),
            stage_names=np.array(names, dtype="U64"),
            stage_embeddings=np.stack(stage_embs),
            stage_levels=np.array(stage_levels, dtype=np.float32),
            stage_level_stds=np.array(stage_stds, dtype=np.float32),
            stage_counts=np.array(stage_counts, dtype=np.int32),
            stage_thresholds=np.array(stage_thresholds, dtype=np.float32),
            calibrated_at=time.time(),
        )
        self._profile = None
        self._profile_mtime = None
        return self.profile_path
