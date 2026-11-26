#!/usr/bin/env python3
"""Guided distance calibration for Mia's speaker gate (terminal version).

    python3 server/scripts/calibrate_voice.py
    python3 server/scripts/calibrate_voice.py --from-files blizu=a.wav srednje=b.wav dalec=c.wav

The HUD has the same flow built in (Settings -> Kalibriraj glas). This CLI is
for headless machines and for scripted setups.
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

from speaker_gate import SpeakerGate, level_db  # noqa: E402

PROFILE = ROOT / "voices" / "speaker_profile.npz"
STAGES = [
    ("blizu", "BLIZU mikrofona (0,5 m)", 4, 2,
     "Stopi čisto blizu mikrofona in reci: Mia, to je moj glas."),
    ("srednje", "SREDNJE oddaljenosti (2–3 m)", 4, 2,
     "Stopi dva do tri metre stran in reci: Mia, ali me slišiš?"),
    ("dalec", "DALEČ (5–6 m)", 5, 2,
     "Pojdi čim dlje, pet do šest metrov, in reci: Mia, to je moj glas."),
]


def record_sample(seconds: int) -> np.ndarray:
    proc = subprocess.run(
        ["timeout", str(seconds), "parec", "--format=s16ne", "--rate=16000", "--channels=1"],
        capture_output=True,
    )
    pcm = np.frombuffer(proc.stdout, dtype=np.int16)
    if pcm.size < 16000:
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
    ap.add_argument("--from-files", nargs="*", default=None,
                    help="stage=path.wav pairs (blizu=a.wav srednje=b.wav dalec=c.wav)")
    ap.add_argument("--append", action="store_true",
                    help="merge with the existing profile instead of replacing it")
    ap.add_argument("--samples", type=int, default=None,
                    help="override captures per stage (default: 2)")
    ap.add_argument("--threshold", type=float, default=0.30)
    args = ap.parse_args()

    gate = SpeakerGate(PROFILE, threshold=args.threshold)
    samples: dict[str, list[np.ndarray]] = {s[0]: [] for s in STAGES}

    if args.from_files:
        for item in args.from_files:
            stage, _, path = item.partition("=")
            if not path:
                raise SystemExit(f"expected stage=path, got {item!r}")
            samples.setdefault(stage, []).append(load_wav(Path(path)))
            print(f"naloženo: {stage} <- {path}")
    else:
        print("KALIBRACIJA GLASU PO ODDALJENOSTI")
        print("Mia bo shranila tvoj glas od blizu, s sredine sobe in od daleč.")
        print("Govori naravno; med posnetki počakaj na znak.\n")
        for stage_id, label, seconds, count, prompt in STAGES:
            count = args.samples or count
            print(f"=== {label} ===")
            print(prompt)
            for i in range(1, count + 1):
                for c in (3, 2, 1):
                    print(f"  posnetek {i}/{count} čez {c} …", end="\r", flush=True)
                    time.sleep(1)
                print(f"  ● POSNAMEM {seconds} s — GOVORI ZDAJ          ", flush=True)
                pcm = record_sample(seconds)
                level = level_db(pcm)
                print(f"  ✓ zajeto {pcm.size / 16000:.1f} s, {level:.1f} dBFS")
                if level < -55:
                    print("  [!] prenizko — naslednjič govori glasneje ali stopi bliže")
                samples[stage_id].append(pcm)
            print()

    print("računam oddaljenostne odtise …")
    path = gate.enroll_distance(samples, append=args.append)
    status = gate.status()
    print(f"\n✓ profil shranjen: {path}")
    for stage in status.get("stages", []):
        print(f"  {stage['name']:<10} {stage['count']} posnetkov · "
              f"{stage['level_db']:.1f} dBFS · prag {stage['threshold']:.2f}")
    print("\nPreizkus: »Mia, koliko je ura?« z razdalje — zdaj bi morala slišati.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
