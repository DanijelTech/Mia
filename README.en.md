# MIA — Voice + HUD for Hermes Agent

> Slovenian documentation: [README.md](README.md) · [docs/](docs/)

A self-hosted, Iron-Man-style voice assistant and command center built on top of
[Hermes Agent](https://github.com/NousResearch/hermes-agent) (NousResearch's
open-source autonomous agent). Talk to a *real* agent — one with persistent
memory, terminal access, web search, file tools, and 80+ skills — through a
glowing arc-reactor HUD in any browser on your LAN, or a push-to-talk client.

**Everything runs on your own hardware.** By default nothing leaves the
machine: Whisper for speech-to-text, a local Piper voice for speech, a local
model (llama-server) behind Hermes, and a local voiceprint for recognizing
your voice. Cloud LLMs and ElevenLabs remain optional — the offline setup
needs no API keys at all.

## Demo

The original upstream project ([eadmin2/jarvis_ai](https://github.com/eadmin2/jarvis_ai))
has a demo video; this fork runs with a local voice engine and a Slovenian UI,
so its look and sound differ.

## What it does

**Just say "Mia, …"** — nothing to click. The HUD starts continuous listening
on load; a VAD (Silero) segments speech, the wake word opens the conversation,
end-of-speech is detected automatically, and the reply streams back as speech,
sentence by sentence, while the rest is still being generated. Typical round
trip with a fast local TTS: 5–10 seconds.

- **Speaker verification (voice calibration)** — Mia obeys only your voice:
  an ECAPA-TDNN voiceprint is checked *before* transcription (~0.1 s), so
  other people and the TV are silently ignored. One-command enrollment,
  multi-language profiles supported (e.g. Slovenian + Serbian):
  `python3 server/scripts/enroll_voice.py`
- **Strict wake word** — reacts only to "Mia …" (tolerates typical Whisper
  mishearings); household noise is dropped without processing, and known
  Whisper hallucinations ("Hvala što pratite" …) are filtered out
- **Half-duplex stability** — no interruptions while processing/speaking
  (noise cannot kill a turn); manual stop remains (STOP button / Esc)
- **Voice pitch slider** — the GLAS panel in the HUD tunes the voice from
  70 to 240 Hz live; applies from the next sentence and persists
- **Speaks Slovenian and Serbian** — replies in the language you speak
- **Opens AND CLOSES desktop windows** — "open Google", "play me some music"
  … and "close it": the `mia-open`/`mia-close` helpers (skills/mia-companion/bin)
  record window ids, so the agent can reliably close what it opened; music
  plays in a dedicated Chrome app window (found via `yt-dlp`)
- **Background tasks** — programming in any folder, files, terminal, web
  search, scheduled jobs, kanban; dangerous actions wait for your ALLOW/DENY
- **Learns your workflows** — the `mia-companion` skill (skills/) tells the
  agent to remember not only preferences but *how* tasks were solved best,
  and to reuse that recipe next time
- **Live agent activity** — watch tool calls happen with command previews
- **Approval cards** — dangerous commands pause for your ALLOW/DENY
- **Embedded dashboards** — kanban, the Hermes dashboard and chat pop up in
  animated viewers (VIEWS), fully interactive
- **Holographic media panels** — say *"show me … on screen"* and a panel
  swoops in from Z-depth; the agent drives it through a bundled Hermes plugin
  (`hud_display`); "clear the screen" sweeps them away
- **Usage tracking** — tokens/day, turns, ElevenLabs quota bar
- **Machines panel** — live CPU/GPU stats for the host and remote workers
- **Privacy filter** — secret-shaped strings are redacted before any text
  reaches cloud TTS
- **Optional GPU ears** — point it at any NVIDIA machine on your LAN running
  the included sidecar and transcription jumps to `large-v3-turbo` at ~0.2 s,
  with automatic fallback to local Whisper when that machine is off
- **Mobile-ready** — responsive layout + Add to Home Screen = full-screen
  Mia app on your phone

## Architecture

```
 Browser HUD (any LAN device)          Host machine (tested: Linux + systemd; macOS with tweaks)
 ── https/wss :8766 ─────────┐   ┌──────────────────────────────────────┐
   mic · speaker · panels    ├──►│ voice pipeline server (this repo)    │
                             │   │  VAD + wake word + speaker voiceprint│   ┌──────────────────┐
 Push-to-talk client         │   │  STT: faster-whisper (local)         │   │ llama-server     │
 ── ws :8765 ────────────────┘   │  TTS: local Piper (or Gepard/Maya1)  ├──►│ (local LLM)      │
                                 │  HUD + auth + TLS proxy              │   ├──────────────────┤
                                 └──────────────────────────────────────┘──►│ Hermes Agent     │
                                             │                              │  API :8642 (lo)  │
                                             └── :9443 proxy ──────────────►│  memory · tools  │
                                                (kanban/dash/chat :9119)    │  skills · cron   │
                                                                             └──────────────────┘
```

One brain, many faces: voice and typed chat share a single persistent Hermes
session, so each knows what you said to the other — and memory survives every
restart.

**Whole-stack management**: with a `stack:` section in `server.yaml`,
`start-mia.sh` boots llama-server (local model) → Hermes gateway → Hermes
dashboard → TTS service → voice server in order (each step skipped when
already up), and `stop-mia.sh` stops everything in reverse, freeing RAM/VRAM.
See `server/config/server.example.yaml`.

## Quick start (one command)

```bash
git clone https://github.com/DanijelTech/Mia.git && cd Mia && sudo ./install.sh --yes --open
```

That single line clones the repo, installs the Python packages into the system
interpreter (no virtualenv), downloads the Slovenian voice, generates the TLS
certificate, adds `MIA_HUD_TOKEN` to `~/.hermes/.env`, writes and starts the
systemd unit, then opens the HUD in your browser **already logged in**
(`?token=` is converted to a cookie and stripped from the URL).

Without root, drop `sudo` — it installs into `pip --user` and `systemctl --user`.
Variants:

```bash
sudo ./install.sh --yes --open --with-maya1   # best Slovenian pronunciation
sudo ./install.sh --yes --open --with-gepard  # lighter GPU voice
./install.sh --dry-run                        # see everything first
```

Afterwards, start/open again at any time with:

```bash
./start-mia.sh                # start (if needed), wait, open the HUD
./start-mia.sh --no-open      # just start and print URL + token
./stop-mia.sh                 # stop the voice server (and the TTS service)
./stop-mia.sh --status        # what is running, which ports are held
./stop-mia.sh --restart       # stop, start again and open
./stop-mia.sh --free-ports    # if a port stays held, kill its owner
./update.sh               # pull the latest release from GitHub and restart
./update.sh --check       # only show what is new
```

The certificate is self-signed, so the browser asks once — accept it.

## Requirements

- A machine for the server (tested: Linux + systemd, 2× GPU for a local 35B
  model; macOS works with tweaks, launchd instead of systemd)
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) installed and
  configured with an LLM provider (by default a local model via llama-server)
- Python 3.11+
- TTS: local **Piper** (default, fast, no key, fully offline), the more natural
  **Gepard** service, the **Maya1** service (best Slovenian pronunciation, slow
  on CPU), or an [ElevenLabs](https://elevenlabs.io) API key for cloud voices —
  the two local services fall back to CPU/RAM when the GPU is busy
- Any modern browser on the LAN
- Optional: `speechbrain` (voice calibration), `yt-dlp` (YouTube music),
  `xdotool` (reliable window closing), `ffmpeg` (pitch shifting)

## Install

One command, no virtualenv (installs into the system Python, which is how a
root Hermes install runs anyway):

```bash
sudo ./install.sh                  # system-wide (root): deps, voice, cert, token, systemd
./install.sh --dry-run             # show every action first
sudo ./install.sh --with-gepard    # + optional Gepard TTS service
sudo ./install.sh --with-maya1     #   or Maya1 (best SL pronunciation)
```

It records everything it creates in a manifest, so removal is exact:

```bash
sudo ./uninstall.sh --dry-run      # preview
sudo ./uninstall.sh                # stop services, remove units, certs, voices, token line
sudo ./uninstall.sh --purge-deps   # ...and pip-uninstall the packages it added
```

Offline machine? `./build-package.sh` produces a tarball (installer included,
no voices) that you can copy over and run with `./install.sh`.

Manual walkthrough (and what the installer automates) is in
[docs/en/SETUP.md](docs/en/SETUP.md). Short version without the installer:

```bash
# 1. Enable the Hermes Agent API server
cat >> ~/.hermes/.env <<EOF
API_SERVER_ENABLED=true
API_SERVER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
MIA_HUD_TOKEN=$(python3 -c 'import secrets;print("mia-"+secrets.token_hex(3))')
ELEVENLABS_API_KEY=your-key-here
EOF
hermes gateway   # or set up its LaunchAgent / service

# 2. This repo
git clone https://github.com/DanijelTech/Mia.git
cd Mia/server
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn requests pyyaml numpy anthropic \
    RealtimeSTT faster-whisper silero-vad websockets psutil
cp config/server.example.yaml config/server.yaml   # edit: your ElevenLabs voice_id etc.
scripts/make-certs.sh                              # self-signed TLS (browser mic needs it)
scripts/make-boot-audio.sh YourName                # one-time boot greeting synthesis

# 3. Local voice (offline, Slovenian/Serbian) — skip if using ElevenLabs
.venv/bin/pip install piper-tts
scripts/get-voice.sh sl

# 4. Run
.venv/bin/python server.py
# open https://YOUR_HOST/hud/ → accept cert → enter your MIA_HUD_TOKEN → talk
```

Offline voice stack (Piper + local Whisper + local LLM, no cloud calls) is
documented in [docs/SETUP.md](docs/SETUP.md#2-the-voice-local-piper-offline-or-elevenlabs-cloud).

For auto-start on boot, see [launchd/](launchd/) (macOS) — the plists document
two non-obvious macOS traps (external-drive TCC and log paths) that cost us an
evening.

## Usage

| Action | How |
|---|---|
| Talk | just say **"Mia, …"** — listening, end-of-speech and reply are automatic |
| Stop the agent | red ■ STOP button or Esc (noise never interrupts mid-turn) |
| Voice pitch | GLAS panel in the HUD — 70–240 Hz slider, applies from the next sentence |
| Voice calibration | `python3 server/scripts/enroll_voice.py` (`--append` for another language) |
| Music | "Mia, play me …" → YouTube app window · "close it / stop the music" |
| Desktop windows | "open Google / \<page\>" and "close it" (mia-open/mia-close) |
| Typed chat | input bar at the bottom (same conversation as voice) |
| Kanban / dashboards | VIEWS panel → kanban, dashboard, chat |
| Push-to-talk | alternative: click the ring (or Space) · speak · click again |
| Phone | open the HUD → Add to Home Screen |

## Repo layout

```
server/          FastAPI voice pipeline + HUD host (the core of this project)
server/hud/      single-file HUD (vanilla JS, no build step)
server/continuous.py  VAD segmentation + wake gate for always-on listening
server/speaker_gate.py  speaker verification (ECAPA-TDNN voiceprints, SpeechBrain)
server/tts.py    local TTS backends: piper, http (Gepard/Maya1), command, elevenlabs
server/scripts/  mia-start/stop/health + enroll_voice.py (voice calibration)
                 + gepard_tts.py (TTS service with per-request pitch)
client/          optional Windows/Linux push-to-talk Python client (wake word capable)
worker/          optional GPU sidecars: big-model STT server + stats agent
hermes-plugin/   Hermes tool plugin: lets the agent summon/dismiss HUD media panels
skills/mia-companion/  Hermes skill: Mia's manners, workflow memory, windows
                 (bin/mia-open + bin/mia-close for reliable open/close)
launchd/         macOS auto-start templates with hard-won TCC + FD-limit notes
docs/            Slovenian docs; docs/en/ the English copies
install.sh       install (no venv, root or user) + manifest
start-mia.sh     boots the whole stack (stack: llama → Hermes → dashboard → Mia + TTS), opens HUD
stop-mia.sh      stops everything and frees RAM/VRAM; status, --restart, --free-ports
update.sh        git pull --ff-only + service restart + Ctrl+Shift+R reminder
uninstall.sh     exact removal of everything install.sh created
build-package.sh offline tarball for a machine without internet
```

## Security model

- The Hermes API key never reaches the browser: the HUD talks through a
  strict allowlist proxy on the voice server.
- All HUD endpoints + dashboard proxy + browser WebSockets are gated by a
  token (cookie, entered once per device).
- Hermes' API binds to loopback only; the dashboard binds to loopback only.
- Secret-shaped strings are redacted before text leaves for cloud TTS.
- LAN-only by design — do not port-forward this to the internet.

## Credits & license

Built on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous
Research. HUD aesthetics inspired by
[jarvis-dashboard](https://github.com/AndrewKochulab/jarvis-dashboard).
STT by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) /
[RealtimeSTT](https://github.com/KoljaB/RealtimeSTT). Voice by
[ElevenLabs](https://elevenlabs.io).

Originally derived from [eadmin2/jarvis_ai](https://github.com/eadmin2/jarvis_ai)
(MIT, © Chris Lassiter); rebranded and extended for local Slovenian/Serbian voice.

MIT — see [LICENSE](LICENSE). Use it, fork it, build your own Mia.
