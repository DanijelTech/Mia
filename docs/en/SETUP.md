# Full Setup Guide

> Slovenian version: [../SETUP.md](../SETUP.md)

## 0. Automated install (recommended)

`install.sh` performs sections 2–5 of this guide in one pass, straight into the
system Python (no virtualenv) — the same way a root Hermes install runs:

```bash
git clone https://github.com/DanijelTech/Mia.git && cd Mia
sudo ./install.sh --dry-run          # 1. see exactly what will happen
sudo ./install.sh --yes --open       # 2. install, start and open the HUD
sudo ./install.sh --with-gepard      #    ...plus the Gepard TTS service
sudo ./install.sh --with-maya1       #    ...or Maya1 (best pronunciation)
```

`--open` waits for the voice server, prints the LAN URL and the access token,
and opens `https://<lan-ip>/hud/?token=…` in the default browser (the HUD turns
that parameter into a cookie and removes it from the address bar). Later:

```bash
./start.sh              # start (if needed), wait, open the HUD
./stop.sh               # stop the server and the TTS service (removes nothing)
./stop.sh --status      # what is running, which ports are held
./stop.sh --restart     # stop, start again, open
./stop.sh --free-ports  # last resort: kill whatever holds the port
```

It installs the Python packages (retrying with `--break-system-packages` when the
distro marks Python as externally managed), downloads the Slovenian voice,
generates the TLS certificate, adds `MIA_HUD_TOKEN` to `~/.hermes/.env` if it is
missing, writes and starts the systemd unit (launchd on macOS), and finishes
with the health check.

Everything it creates is written to a manifest
(`/var/lib/mia/install-manifest.json` for root, `~/.local/state/mia/...` for a
user install). `uninstall.sh` uses that manifest, so removal is exact:

```bash
sudo ./uninstall.sh --dry-run        # preview
sudo ./uninstall.sh                  # stop+disable service, remove unit, certs,
                                     # voices, boot audio, logs, server.yaml, token line
sudo ./uninstall.sh --purge-deps     # also pip-uninstall the recorded packages
sudo ./uninstall.sh --keep-data      # keep voices/certs/logs/config
```

It never touches Hermes, its sessions/memory, your models, or the source tree.

**Non-root installs** adapt automatically: port 443 cannot be bound without
privileges, so the installer writes `tls_ports: [8766]` and the HUD lives at
`https://<lan-ip>:8766/hud/` (also printed in the summary). Because it is a user
systemd unit, keep it alive after logout with `loginctl enable-linger $USER`.
For port 443 later, re-run the installer with `sudo`.

To build a tarball for an offline machine: `./build-package.sh`.

Tested on macOS (Apple Silicon) with Hermes Agent v0.16. Allow ~1 hour.

## 1. Hermes Agent (the brain)

Install Hermes Agent and give it an LLM provider — follow the
[official quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart).
Verify `hermes` works in your terminal before continuing.

Enable its API server in `~/.hermes/.env`:

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=<long random secret>      # required — full toolset incl. terminal!
```

Start the gateway (`hermes gateway`) and verify:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
# {"status": "ok", ...}
```

Recommended: add voice-behavior rules to your global `~/.hermes/SOUL.md`
(short spoken sentences, no markdown aloud, never speak secrets, announce risky
actions and wait for approval). The agent — not the voice server — should own
its personality.

### Keep the Hermes gateway running

Mia talks to Hermes at `127.0.0.1:8642` — **Mia calls Hermes**, not the other way
round (Hermes only connects to Mia if you install the optional `hud_display`
plugin). A gateway started in a terminal dies with it: the HUD then shows
"Hermes API offline" and Mia says "Hermes gateway unreachable" out loud.

Hermes ships its own service manager — use that instead of hand-written units:

```bash
hermes gateway install --start-now --start-on-login   # systemd/launchd service
hermes gateway status                                 # is it running (PID, service)
hermes gateway list                                   # profiles and their gateways
tail -n 40 ~/.hermes/logs/gateway.log                 # which platforms started
```

Whether `api_server` really started shows up in the log (an `API Server` line) and
in `curl` on 8642. If the log says **`API Server: aiohttp not installed`**, the
gateway skips the platform silently — install `aiohttp` in the Hermes runtime and
restart:

```bash
python3 -m pip install --user aiohttp     # or into Hermes' own venv, if it uses one
hermes gateway restart
```

Boot-time without login (Linux, root):

```bash
sudo hermes gateway install --system --run-as-user "$USER" --start-now
```

**Important:** the `api_server` platform (OpenAI-compatible API on 8642) is only
enabled when the gateway sees `API_SERVER_ENABLED=true` **or** `API_SERVER_KEY`
in its environment. `API_SERVER_PORT` / `API_SERVER_HOST` change the bind. With
profiles, each profile has its own `.env` — check `hermes gateway list`.

Verify the port really listens:

```bash
curl -s -m 2 http://127.0.0.1:8642/health && echo OK || echo "nothing on 8642"
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
```

A hand-written systemd unit is only a fallback if `hermes gateway install` does
not work on your platform. Quick and dirty: `nohup hermes gateway >> ~/.hermes/gateway.log 2>&1 &`.

## 2. The voice: local Piper (offline) or ElevenLabs (cloud)

Default is **local Piper** — no API key, no network, ~0.7 s to synthesize a
sentence on CPU (4–6× realtime):

```bash
.venv/bin/pip install piper-tts          # GPL-3.0, used as a subprocess
scripts/get-voice.sh sl                  # Slovenian (63 MB) — or `all` for sl + sr
```

Voices land in `server/voices/` (gitignored). Then in `config/server.yaml`:

```yaml
tts:
  provider: piper
  piper:
    language: sl                         # sl | sr — picks from `voices`
    voices:
      sl: voices/sl_SI-artur-medium.onnx
      sr: voices/sr_RS-serbski_institut-medium.onnx
```

Other local engines plug in through `tts.provider: command`: any binary that
reads text on stdin and writes a WAV (or raw PCM16) on stdout — e.g. a Gepard
or Maya1 wrapper. `tts.provider: elevenlabs` remains available for cloud use:
create a key at elevenlabs.io, pick a `voice_id`, add `ELEVENLABS_API_KEY` to
`~/.hermes/.env`, and give the key the **User → Read** permission for the HUD
quota bar. Note Flash v2.5 does not cover Slovenian or Serbian; use
`eleven_v3_conversational` there.

### Female / gentle voice — where to set it

Everything lives in `server/config/server.yaml` (the `tts:` block) plus, for the
service engines, the arguments the service is started with:

| Engine | Female Slovenian voice? | Where |
|---|---|---|
| **Piper** (default, CPU) | **no** — the only Slovenian voice (`artur`) is male | `tts.piper.length_scale: 1.1` (slower = calmer); `tts.piper.speaker` only for multi-speaker models |
| **Maya1** (local, GPU) | **experimental** — English voice description | `tts.http.args: ["--maya-voice", "zenski-nezni"]` or `["--maya-description", "…"]` |
| **ElevenLabs** (cloud) | **yes** — pick a female voice | `tts.provider: elevenlabs`, `tts.elevenlabs.voice_id`, `model: eleven_v3_conversational` |

Maya1 presets: `zenski`, `zenski-nezni`, `zenski-veseli`, `moski`, `starejsi`,
`nevtralno`. Honest caveat: the adapter was trained on ARTUR speaker IDs, so
gender control is a nudge rather than a guarantee — try two or three
descriptions. `curl localhost:8770/health` shows the active `description`.

After changing:

```bash
./install.sh --yes            # rewrites the systemd unit with the new args
systemctl --user restart mia-tts mia-voice
```

ElevenLabs needs `ELEVENLABS_API_KEY` and works with `eleven_v3_conversational`
(`eleven_flash_v2_5` does **not** cover Slovenian). Piper has no female Slovenian
voice; `length_scale: 1.1` only slows it down.

### Better voice: Gepard (optional, GPU with RAM offload)

Piper is clear but flat. [texdata/Gepard-Slovenian-TTS](https://huggingface.co/texdata/Gepard-Slovenian-TTS)
(Apache-2.0 LoRA, ~555 M, 22 kHz) has noticeably more natural Slovenian prosody.
It is heavier than Piper, so it runs as a **service** — the model loads once, not
per sentence:

```bash
.venv/bin/pip install accelerate
.venv/bin/pip install "nemo_toolkit[tts]"
.venv/bin/pip install git+https://github.com/nineninesix-ai/gepard-inference

# start it (device picked automatically, see below)
.venv/bin/python scripts/gepard_tts.py --serve --port 8770 \
    --engine gepard --fallback-piper
```

Then point the voice server at it:

```yaml
tts:
  provider: http
  http:
    url: http://127.0.0.1:8770/tts
    format: wav
    timeout: 120
    name: gepard
```

**GPU vs RAM offload.** The service picks its device at startup:
`--device auto` (default) uses CUDA only when at least `--min-free-vram-gb`
(3 GB) is actually free; otherwise it runs on CPU/RAM. With `--offload auto` it
first tries an accelerate `device_map` split (part GPU, part RAM), then falls
back to pure CPU, and if the CUDA load itself fails it retries on CPU instead of
crashing. That is what keeps Mia alive on a box where the LLM already owns the
GPU:

| Qwen3-30B-A3B | Whisper large-v3-turbo | Gepard | Fits 32 GB? |
|---|---|---|---|
| Q4_K_M ~18.6 GB | ~1.6 GB | ~2 GB | yes, comfortable |
| Q5_K_M ~21.7 GB | ~1.6 GB | ~2 GB | yes |
| Q6_K ~26.7 GB | ~1.6 GB | ~2 GB | tight — TTS drops to CPU |
| Q8_0 ~32.5 GB | — | — | GPU is full — TTS and STT use CPU/RAM |

`--fallback-piper` means: if the Gepard stack is missing or fails to load, the
service still answers with the Piper voice instead of leaving Mia mute.
Check what it chose with `curl -s localhost:8770/health` (`device`, `reason`,
`free_vram_gb`).

The same service can run on a second machine (e.g. the GPU workstation) — just
put its address in `tts.http.url` and set `MIA_HUD_TOKEN` on both sides; the
token is sent as `X-Mia-Token`.

For a permanent start use systemd (`systemd --user`, `ExecStart=.../gepard_tts.py
--serve --port 8770`) or `nohup ... &` on Linux, and Task Scheduler on Windows.

Note: the LoRA card is Apache-2.0; check the base model
(`nineninesix/gepard-1.0`) and the NeMo codec licenses before redistributing.

### Sharing the GPU with your LLM (important)

Whisper can run on GPU or CPU. **If the LLM runs on the same card, keep Whisper
on CPU** (`stt.device: cpu`, the default in the example config): on GPU it holds
~1.6 GB for the model plus ~0.5–0.8 GB of CUDA context (~2.4 GB), and launchers
that check free VRAM before loading the LLM will refuse to start. If you do want
GPU STT, start the LLM first so Mia sees less free VRAM (or set `cpu`), and use
`./install.sh --stt-device cpu|cuda|auto` to switch. For fast STT *and* a local
LLM, put the STT worker on another machine (`stt.remote`).

### Best pronunciation: Maya1 (optional, GPU with RAM offload)

[Maya1 Slovenian TTS](https://huggingface.co/texdata/Maya1-Slovenian-TTS)
(Apache-2.0) is a LoRA on the 3B `maya-research/maya1` Orpheus-style speech LM
with a **phoneme front-end**: text is converted to espeak-ng `sl` IPA before
generation, which fixes the stress and č/š/ž problems grapheme models have (the
author measures the lowest character error rate of their variants, 4.2% vs 5.0%
for grapheme). It is the heaviest and slowest of the three local voices.

```bash
sudo ./install.sh --with-maya1        # deps + espeak-ng + systemd unit
# or manually:
pip install transformers peft snac soundfile phonemizer accelerate
sudo apt-get install espeak-ng        # macOS: brew install espeak
scripts/gepard_tts.py --serve --port 8770 --engine maya1 --fallback-piper
```

Point Mia at it exactly like Gepard (`tts.provider: http`, `url:
http://127.0.0.1:8770/tts`).

| | Piper | Gepard | Maya1 |
|---|---|---|---|
| VRAM | 0 (CPU) | ~2 GB | ~6–7 GB (bf16) |
| Speed | 4–6× realtime | ~0.5–2 s per sentence on GPU | slowest (3B autoregressive) |
| Quality | clear, flat | natural-ish | best Slovenian pronunciation |
| Extras | `piper-tts` | NeMo + `gepard-inference` | `transformers`/`peft`/`snac`/`phonemizer` + espeak-ng |

Voice control: `--maya-emotion nevtralno|veselo|jezno|gnus|zaspano` swaps the
English voice description (the Slovenian adapter was fine-tuned on neutral read
speech, so emotional range is limited). `--temperature` defaults to 0.75 for
Maya1 (0.4 for Gepard); `--maya-max-new-tokens` bounds the generation (~1800 ≈
10 s). The built-in `repetition_penalty=1.1` matters: without it short inputs can
fail to emit the end token.

On a 32 GB card with Qwen3-30B-A3B **Q4** (~18.6 GB) + Whisper (~1.6 GB) Maya1
fits (~26 GB total). With Q5/Q6 it first tries the accelerate GPU/RAM split, then
CPU; on CPU a sentence takes tens of seconds, so Piper or Gepard is the better
choice there.

Licences: adapter and base model are Apache-2.0; the SNAC codec
(`hubertsiuzdak/snac_24khz`) carries its own — check before redistributing.
Citation: Tadej Fius, MediaAtlas (see the model card).

### Fully offline checklist

| Item | Setting |
|---|---|
| TTS | `tts.provider: piper` (no key needed) |
| LLM | local model behind Hermes (`hermes.base_url` → 127.0.0.1) |
| STT | local Whisper (`stt.model: large-v3-turbo`) |
| Cloud fallback | `hermes.fallback_provider: ""` |
| External media panels | `hud.allow_external_media: false` |
| Fonts | self-hosted in `server/hud/fonts/` |

Verify: `curl -s localhost:8765/api/hud-config` returns
`"tts_provider": "piper"` and `"allow_external_media": false`, and
`/api/usage` returns `"elevenlabs": null` (no outbound request).

### Upgrading an existing install (jarvis_ai → Mia)

Everything user-visible is renamed, but the old names keep working so you can
migrate at your own pace:

| Old | New | Compatibility |
|---|---|---|
| `JARVIS_HUD_TOKEN`, `JARVIS_STT_*`, `JARVIS_SUMMON_URL`, `JARVIS_WORKER_NAME` | `MIA_*` | old env vars are still read when the new one is unset |
| cookie `jarvis_token`, header `X-Jarvis-Token` | `mia_token`, `X-Mia-Token` | both accepted on input |
| `jarvis.local`, `jarvis` | `mia.local`, `mia` | both allowed as HUD origins |
| `scripts/jarvis-*.sh` | `scripts/mia-*.sh` | old names removed — update your aliases/cron |
| `com.jarvis.voice`, `com.jarvis.dashboard` | `com.mia.voice`, `com.mia.dashboard` | old LaunchAgents keep running until you swap them |
| `hud/jarvis.cer` | `hud/mia.cer` | phones must install the new profile (old cert still trusted) |

Two changes are not cosmetic:

- **`hermes.session_key`** went from `jarvis:user:main` to `mia:user:main`.
  That starts a fresh long-term memory scope. To keep the old memories, set
  `session_key: jarvis:user:main` back in `config/server.yaml`.
- **launchd** needs a swap on macOS:
  ```bash
  launchctl bootout gui/$(id -u)/com.jarvis.voice 2>/dev/null
  launchctl bootout gui/$(id -u)/com.jarvis.dashboard 2>/dev/null
  cp launchd/com.mia.*.plist ~/Library/LaunchAgents/
  scripts/mia-start.sh
  ```

## 3. The voice pipeline server (this repo)

```bash
cd server
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn requests pyyaml numpy anthropic \
    RealtimeSTT faster-whisper silero-vad websockets psutil
cp config/server.example.yaml config/server.yaml
```

Note: `faster-whisper` and `silero-vad` are REQUIRED — recent RealtimeSTT
releases treat them as optional extras and fail at runtime without them
(silently for VAD, loudly for the engine). The first start takes 60–90 s
(torch import + model download); subsequent starts are faster.

Edit `config/server.yaml`: set `voice.voice_id`, and adjust the `machines:`
list (or delete it). The first run downloads the Whisper model (~460 MB for
`small.en`).

### TLS certificates (required for browser microphone)

Browsers only expose the mic to secure origins:

```bash
scripts/make-certs.sh            # auto-detects your LAN IP for the SAN
```

Trust `certs/cert.pem` on each device (macOS: Keychain; Windows:
`certutil -user -addstore Root cert.pem`; iPhone: download
`https://host:8765/hud/mia.cer`, install profile, then enable in
Settings → General → About → Certificate Trust Settings).

Optional but nice: rename your host's mDNS name (`sudo scutil --set
LocalHostName mia` on macOS) so the HUD lives at `https://mia.local/hud/`.
Port 443 needs the wildcard bind already set in the example config.

### HUD access token

```bash
echo "MIA_HUD_TOKEN=mia-$(python3 -c 'import secrets;print(secrets.token_hex(3))')" >> ~/.hermes/.env
```

The HUD asks for this once per device. Omit the variable entirely to disable
auth (not recommended).

### Boot greeting (one-time, local)

```bash
scripts/make-boot-audio.sh YourFirstName    # writes hud/audio/boot_*.wav
```

Uses the same local Piper voice — no cloud characters spent.

### Run it

```bash
.venv/bin/python server.py
```

Wait ~40 s for the STT model to warm, then open `https://YOUR_HOST/hud/`.
Run `scripts/mia-health.sh` to check all five services.

## 4. Auto-start on boot (macOS)

Copy the two plists from `launchd/`, edit the `/PATH/TO` and `YOUR_USER`
placeholders, then:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mia.voice.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mia.dashboard.plist
```

**Read the comments in the plists** — there are two macOS traps (external-drive
TCC permissions and log-path location) that produce silent hangs or `EX_CONFIG`
errors if ignored. Day-to-day management: `scripts/mia-{start,stop,restart,health}.sh`.

## 5. Optional extras

**Push-to-talk client** (Windows/Linux box with a mic):

```bash
cd client
python -m venv .venv && .venv/Scripts/pip install sounddevice websockets numpy openwakeword
python client.py --push-to-talk --server ws://YOUR_HOST:8765/ws --list-devices
```

**GPU worker stats** (shows in the Machines panel): copy
`worker/worker_stats.py` to the worker machine, `pip install psutil`, run it,
and point a `machines:` entry's `stats_url` at `http://worker-ip:8767/stats`.

**GPU speech recognition** — the single biggest quality upgrade if you own any
NVIDIA machine on the LAN. On that machine:

```
cd worker
python -m venv .venv
.venv/Scripts/pip install faster-whisper fastapi uvicorn nvidia-cublas-cu12 nvidia-cudnn-cu12
copy run-stt.example.bat run-stt.bat    # fill in your MIA_HUD_TOKEN value
run-stt.bat
```

Then uncomment the `stt.remote:` block in the server's `server.yaml` (point
`url` at the GPU machine) and restart the voice server. Result: `large-v3-turbo`
accuracy at ~0.2 s per utterance, with automatic fallback to the local model
whenever the GPU machine is off. For auto-start at Windows logon, drop a
`MiaSTT.vbs` in `shell:startup` (template in the .bat comments).

**Phone app feel**: open the HUD in Safari/Chrome on your phone →
Share → Add to Home Screen.

**Let the agent put things on your screen** (the showstopper): install the
bundled Hermes plugin so "show me a video of X on screen" makes holographic
media panels materialize on every open HUD:

```bash
cp -R hermes-plugin/hud_display ~/.hermes/plugins/hud_display
# edit ~/.hermes/plugins/hud_display/schemas.py: replace YOUR_HOST
hermes plugins enable hud_display     # repeat with -p <profile> if you use profiles
# restart your hermes gateway
```

The plugin needs `MIA_HUD_TOKEN` in `~/.hermes/.env` (same token as the
HUD). Directory name must stay a valid Python module name — hyphens silently
break plugin discovery. The agent then has `hud_display` / `hud_dismiss`
tools; YouTube links play as embedded video, `position` left/right lets it
fly in multiple panels from different vectors.

## 6. Verify everything

**Updating to a new release:**

```bash
cd ~/Mia && ./update.sh          # git pull --ff-only + service restart
./update.sh --check              # only show what is new
```

Your `server/config/server.yaml`, voices and certificates are gitignored and are
not touched by an update; if the installer or the systemd unit changed,
`update.sh` says so and suggests `./install.sh --yes`.

```bash
scripts/mia-health.sh   # all five rows OK
scripts/mia-smoke.sh    # synthesized voice turn through the full stack (macOS)
```

Then the real test: click the ring and ask "what's in your memory file?" —
a real agent answers with real file contents.
