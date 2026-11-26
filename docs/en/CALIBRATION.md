# Distance voice calibration

Mia recognises only the enrolled speaker, anywhere in the house. The profile
stores a separate ECAPA voiceprint for **near**, **mid-room** and **far**
captures, plus the measured level (dBFS) and a calibrated threshold per stage.

## HUD flow

On first start the HUD shows **KALIBRACIJA GLASU PO ODDALJENOSTI**:

- near (~0.5 m), 4 s × 2
- mid-room (2–3 m), 4 s × 2
- far (5–6 m), 5 s × 2

Mia speaks the prompt, captures the reply, rejects captures below −55 dBFS,
and finally writes `server/voices/speaker_profile.npz`. No restart is needed:
the gate reloads on mtime change.

Repeat any time from **NASTAVITVE → KALIBRIRAJ GLAS**.

## Terminal

```bash
python3 server/scripts/calibrate_voice.py
python3 server/scripts/calibrate_voice.py --samples 3
python3 server/scripts/calibrate_voice.py --from-files blizu=a.wav srednje=b.wav dalec=c.wav
```

## Strict wake

```yaml
stt:
  continuous:
    wake_words: ["mia", "mijo", "mija", "mio"]
    strict_wake: true
    followup_seconds: 0
    speaker_gate:
      enabled: true
      threshold: 0.30
      require_profile: false
      calibration:
        required: true
```

- Every turn must start with “Mia”.
- With a calibrated profile, other voices/noise are rejected before Whisper.
- `require_profile: true` refuses speech until calibration exists (the HUD can
  always start calibration).
- The HUD **NASTAVITVE** page changes these live and persists them in
  `server/logs/settings.json`.

## Profile format

`embedding` (overall centroid), `samples`, `stage_names`,
`stage_embeddings`, `stage_levels`, `stage_level_stds`, `stage_counts`,
`stage_thresholds`. Verification embeds once, compares against every centroid
and uses the best score with that stage's threshold (short clips get +0.05).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Mia hears nothing | `require_profile: true` and no profile → calibrate |
| Mia hears the TV | calibrate, raise threshold |
| Far speech missed | more far samples, lower threshold slightly |
| Mic changed | recalibrate with the same microphone |
