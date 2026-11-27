# Credits and third-party notices

Mia is an independent, local-first project. This file lists the open-source
components and upstream work that made it possible. **No mention here is an
endorsement, sponsorship or partnership.** Each project keeps its own license;
check its repository for the exact terms and version you install.

## Upstream and inspiration

- **jarvis_ai** by Chris Lassiter (`eadmin2/jarvis_ai`, MIT) — the original
  MIT copyright notice is preserved in [`LICENSE`](LICENSE). Mia has since been
  substantially rewritten; the current architecture, HUD, learning core,
  autonomy layer and installers are Mia's own.
- **Hermes Agent** (NousResearch) — the local agent runtime Mia connects to for
  tools, sessions, memory and approvals. Mia is not affiliated with or endorsed
  by NousResearch.

## Speech and voice

- **faster-whisper** (SYSTRAN) — local speech recognition.
- **RealtimeSTT** (KoljaB) — streaming audio/STT plumbing.
- **Silero VAD** — voice activity detection.
- **SpeechBrain** — speaker embeddings for the optional voice gate.
- **Piper** (rhasspy/piper) — fast local neural voices; individual voice models
  have their own licenses.
- **Gepard** and **Maya1** — optional local voice engines; see their upstream
  repositories for model and code licenses.
- **ElevenLabs** — optional cloud voice, used only when explicitly configured.

## Local model runtime

- **llama.cpp / llama-server** (ggml-org) — local OpenAI-compatible model
  server.
- **Model weights** — each model has its own license and usage terms. Mia does
  not redistribute model weights.

## Python and web stack

- **FastAPI** (MIT), **Uvicorn** (BSD-3-Clause), **Starlette** (BSD-3-Clause)
- **NumPy** (BSD-3-Clause), **PyYAML** (MIT), **requests** (Apache-2.0)
- **psutil** (BSD-3-Clause), **websockets** (BSD-3-Clause)
- **uvicorn/websockets** and the browser WebSocket/WebAudio APIs

## Fonts

- **Orbitron** and **Rajdhani** — SIL Open Font License 1.1; the WOFF2 files in
  `server/hud/fonts/` are served locally so the HUD works offline.

## Icons and visual assets

- The HUD is drawn with CSS, canvas and inline SVG in this repository. No
  third-party icon pack is required.
- `docs/images/hud-en.png` is a screenshot of this repository's HUD.

## How to correct this file

If a component is missing, misattributed or its license changed, open a
[documentation issue](https://github.com/DanijelTech/Mia/issues/new?template=bug_report.yml)
or send a PR. This file is informational; the license text that governs your
use of Mia is [`LICENSE`](LICENSE).
