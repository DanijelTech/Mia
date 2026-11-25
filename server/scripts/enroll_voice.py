#!/usr/bin/env python3
"""Enroll the user's voice so Mia reacts only to them (speaker gate).

    python3 scripts/enroll_voice.py                 # record 3 x 6 s from the default mic
    python3 scripts/enroll_voice.py --from-files a.wav b.wav ...   # use existing recordings

The profile lands in voices/speaker_profile.npz (gitignored); the running
voice server picks it up on the next utterance — no restart needed.
Re-run any time to recalibrate.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from speaker_gate import SpeakerGate  # noqa: E402

PROFILE = ROOT / "voices" / "speaker_profile.npz"
SAMPLE_SECONDS = 6
SAMPLES = 3


def record_sample(seconds: int) -> np.ndarray:
    """Record from the default PulseAudio/PipeWire source (16 kHz mono s16)."""
    proc = subprocess.run(
        ["timeout", str(seconds), "parec", "--format=s16ne", "--rate=16000", "--channels=1"],
        capture_output=True,
    )
    pcm = np.frombuffer(proc.stdout, dtype=np.int16)
    if pcm.size < 16000:  # < 1 s of audio
        raise RuntimeError("snemanje ni uspelo (premalo zvoka) — preveri mikrofon")
    return pcm


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError(f"{path}: potreben je mono 16-bit WAV")
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        rate = w.getframerate()
    if rate != 16000:
        idx = np.arange(0, len(pcm) - 1, rate / 16000)
        pcm = np.interp(idx, np.arange(len(pcm)), pcm.astype(np.float32)).astype(np.int16)
    return pcm


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-files", nargs="*", type=Path, default=None,
                    help="existing mono WAV recordings instead of the microphone")
    ap.add_argument("--samples", type=int, default=SAMPLES,
                    help=f"how many recordings to take (default {SAMPLES}; use more "
                         "when mixing languages, e.g. 2x Slovenian + 2x Serbian)")
    ap.add_argument("--append", action="store_true",
                    help="ADD to the existing profile instead of replacing it "
                         "(e.g. enrol Serbian on top of Slovenian)")
    args = ap.parse_args()

    gate = SpeakerGate(PROFILE)
    samples: list[np.ndarray] = []

    if args.from_files:
        for p in args.from_files:
            samples.append(load_wav(p))
            print(f"naloženo: {p}")
    else:
        print("KALIBRACIJA GLASU — govori naravno, kot bi se pogovarjal z Mio.")
        print("Nekaj predlogov: »Mia, koliko je ura?«, »Mia, odpri mi splet.«")
        if args.append:
            print("(dodajanje obstoječemu profilu — govori v jeziku, ki ga dodajaš)\n")
        for i in range(1, args.samples + 1):
            for c in (3, 2, 1):
                print(f"  posnetek {i}/{args.samples} čez {c} …", end="\r", flush=True)
                time.sleep(1)
            print(f"  ● POSNAMEM {SAMPLE_SECONDS} s — GOVORI ZDAJ          ", flush=True)
            samples.append(record_sample(SAMPLE_SECONDS))
            print(f"  ✓ posnetek {i} zajet ({samples[-1].size / 16000:.1f} s)\n")

    print("računam glasovni odtis …")
    path = gate.enroll(samples, append=args.append)

    # self-check: how well do the samples match the profile, pairwise spread
    scores = [float(np.dot(gate.embed(s), np.load(path)["embedding"])) for s in samples]
    print(f"\n✓ profil shranjen: {path}")
    print(f"  ujemanje posnetkov s profilom: {[f'{s:.2f}' for s in scores]}")
    print(f"  prag v configu (stt.continuous.speaker_gate.threshold): "
          f"{min(scores) - 0.10:.2f} ali nižje, da se tebi nikoli ne zanika")
    print("\nPreizkus: »Mia, koliko je ura?« — tuj glas se zdaj ignorira "
          "(v dnevniku: SPEAKER rejected).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
