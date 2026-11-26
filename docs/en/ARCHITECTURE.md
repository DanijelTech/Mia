# Architecture & Protocols

> Slovenian version: [../ARCHITECTURE.md](../ARCHITECTURE.md)

## How a voice turn flows

1. Browser captures mic at 16 kHz mono (AudioContext created at 16 kHz —
   avoids resampling artifacts that wreck Whisper accuracy) and streams int16
   PCM over WebSocket `/ws`.
2. While you speak, the server runs incremental Whisper passes every ~1.2 s
   and emits `partial_transcript` events (live captions).
3. On stop: final transcription — the server first tries the optional **GPU
   STT worker** (`stt.remote`, big model, ~0.2 s) and falls back to local
   Whisper if it's unreachable — then the transcript goes to Hermes via its **Sessions
   API** (`POST /api/sessions/{id}/chat/stream`, SSE). Session ids persist in
   `logs/hermes_sessions.json` per conversation name, so memory survives
   restarts. Typed chat (`/api/chat`) uses the *same* session.
4. SSE events parsed: `run.started` (run id → STOP support), `assistant.delta`
   (text), `tool.started` (name + preview → HUD activity), `assistant.completed`
   (incl. `interrupted` flag), `run.completed` (token usage), `*approval*`
   (→ HUD approval cards).
5. Text is sentence-split, markdown/think-block-stripped, **secret-redacted**,
   then each sentence streams through the configured TTS backend (`server/tts.py`:
   local `piper` by default, `http` for a local TTS service such as Gepard,
   `command` for a per-sentence local CLI, or `elevenlabs` for cloud) back to the
   client as 16 kHz PCM while generation continues. Local voices at 22.05 kHz are
   resampled streamingly in-process.

Why the Sessions API and not `/v1/responses` or `/v1/runs`: on Hermes v0.16,
sessions are the only surface that combines named persistent memory, run ids,
tool events, and approval events in one stream.

## Learning, memory and the skill tree

Before each turn the server builds a bounded `[MIA SPOMIN …]` brief from the
local SQLite store (`server/mia_core/`): relevant habits, recipes,
anti-patterns and facts. The brief is prepended to the Hermes payload and
limited by `learning.context.max_chars` (default 1500). After the turn an
episode is recorded (request, response, tools, outcome, duration, errors,
entities); successful episodes with tools become recipes, failures become
anti-patterns.

Short phrases ("right", "not right", "remember this procedure") are handled
deterministically on the previous episode before reaching Hermes. Every
`auto_mine_interval_seconds` (900 s) the server mines habits, ingests
`control-audit.jsonl` and refreshes the skill index. Learning fails open: a
broken DB never takes the voice loop down.

The skill tree (`skills/`) is explicit: `mia-companion` is the root and the
children (`mia-desktop`, `mia-learning`, `mia-music`, `mia-browser`,
`mia-productivity`, `mia-diagnostics`) own individual domains.
`mia-skill validate` checks names, parents and `references/`.

## Local computer control

`mia-ctl` (in `skills/mia-companion/bin/`) is the recommended interface for
actions on the machine. Every call checks the policy
(`~/.config/mia/control.json`), runs commands as argument lists (never
`shell=True`) and writes an audit record to
`~/.local/state/mia/control-audit.jsonl`. The audit is ingested into the
learning store, so control actions become part of habits and recipes.

## Autonomy (mini sub-OS)

`server/mia_core/autonomy/` is a stdlib-only layer above `mia-ctl`:

- `profile.py` detects the machine (OS, distro, init, package manager, desktop,
  tools, GPU, battery, network, privileges, container), picks a backend per
  capability, scores readiness and produces an adaptation plan with package
  names for this distribution. Snapshots and diffs are persisted.
- `planner.py` executes plans (`ctl`/`python`/`notify`/`sleep`/`probe`/
  `wait_for`/`plan` steps) with policy preflight, post-condition verification,
  retries, rollback and a SQLite journal. Tasks can be resumed.
- `scheduler.py` stores persistent jobs (`at`, `every`, `daily`) and rules
  (`condition`, `event`, `idle`). Condition rules are edge-triggered with
  `for_seconds`, preventing notification storms.
- `health.py` checks disk, RAM, swap, load, temperature, battery, network,
  systemd failures, certificate, learning DB and stale tasks; it returns a
  score, alerts and safe remediation.
- `intents.py` is the deterministic Slovenian/English system command router; it
  only catches anchored patterns, otherwise the sentence reaches Hermes.
- `service.py` is the shared facade used by the voice loop, `/api/chat`,
  `/api/autonomy/*` and the HUD.

The server ticks the scheduler every `autonomy.interval_seconds` (30 s) and the
health check every `health_interval` (300 s). The whole layer is fail-open: a
broken profile or DB never stops the voice loop.

## Calibration, settings and verification

- The HUD can start a guided distance calibration over the same WebSocket:
  `calibration_start` → `calibration_state` (near/mid/far prompts) →
  `calibration_done`. The server stores per-distance centroids and levels.
- `/api/settings` reads/writes strict wake, follow-up, speaker threshold,
  require-profile, verification prompts, learning and brief length; changes
  are applied live and persisted in `server/logs/settings.json`.
- `/api/capabilities` exposes the confirmed/learned/detected/empty checklist.
- `/api/learning/pending` feeds the HUD ✓/✗ cards; `/api/learning/verify`
  records the verdict and promotes only confirmed procedures to recipes.

## WebSocket protocol (voice clients)

Client → server (JSON + binary):

```
{"type":"start","sample_rate":16000,"format":"pcm_s16le","channels":1,"conversation":"mia-main"?}
<binary int16 PCM chunks>
{"type":"stop"}
{"type":"stop_run"}
{"type":"approval_decision","run_id":...,"approval_id":...,"decision":"allow"|"deny"}
```

`start` during an active turn = barge-in: the server cancels the turn, stops
the Hermes run, records the last spoken sentence, and prefixes the next turn's
input with an interruption note so the agent's memory matches what you heard.

Server → client:

```
status · partial_transcript · transcript · run_started{run_id}
agent_status{state: thinking|tool_use(+tool,preview)|speaking|stopped}
approval_request{data,run_id} · error · done{timing}
<binary TTS PCM — frames split at arbitrary byte boundaries; buffer odd bytes>
```

## HTTP endpoints (voice server)

| Endpoint | Purpose |
|---|---|
| `/hud/` | the HUD (static, single file) |
| `/api/hermes/{path}` | **allowlist** proxy to Hermes API, injects the bearer key (GET: health, capabilities, skills, toolsets, jobs, sessions; POST: v1/responses only) |
| `/api/chat` | typed chat turn on the shared voice session |
| `/api/learning/status` | memory, DB and skill tree status |
| `/api/learning/tree` | skill tree (flat + nested + health) |
| `/api/learning/brief` | exact brief the model would receive for a request |
| `/api/learning/search` | search episodes, recipes, mistakes and facts |
| `/api/learning/habits`, `/recipes`, `/mistakes`, `/facts`, `/episodes`, `/events` | memory views |
| `/api/learning/feedback`, `/remember` | ✓/✗ feedback and recipe promotion |
| `/api/learning/recipe`, `/mistake`, `/fact` | manual entries |
| `/api/learning/mine`, `/prune`, `/sysinfo`, `/delete`, `/export` | maintenance |
| `/api/autonomy/status`, `/profile`, `/health`, `/jobs`, `/tasks`, `/alerts` | autonomy state, machine profile, health, jobs, tasks, alerts |
| `/api/autonomy/refresh`, `/adapt`, `/remediate`, `/tick`, `/run`, `/text` | detect/adapt, remediate, one scheduler cycle, run a plan, natural command |
| `/api/autonomy/jobs` (POST/DELETE), `/jobs/{id}/toggle`, `/tasks/{id}/resume`, `/cancel` | manage jobs and tasks from the HUD |
| `/api/machines` | host psutil stats + remote workers from config |
| `/api/usage` | local token/char tally; ElevenLabs quota only when TTS is cloud-based |
| `/api/hud-config` | HUD switches: `allow_external_media`, reply `language`, `tts_provider` |
| `/api/summon` | broadcasts a holographic media panel (`{media, src, title, position}` or `{action:"dismiss"}`) to every connected HUD over its WebSocket — this is what the bundled `hud_display` Hermes plugin calls |
| port 9443 (separate app) | TLS reverse proxy of the Hermes dashboard with WebSocket bridge and frame-header stripping, so the HTTPS HUD can iframe it |

## Auth model

`MIA_HUD_TOKEN` (env) gates `/api/*`, the dashboard proxy, and
browser-originated WebSockets (Origin allowlist + cookie). Native clients (the
PTT client, test scripts) send no Origin header and are exempt — the
threat model is a malicious *website* doing cross-origin requests against your
LAN, not your own processes. The Hermes API key never reaches any browser.

## Latency profile (Apple Silicon, local Whisper + Piper)

STT finalize ~0.7 s · Hermes first token 1–3 s (more with tools) · first
audible audio ~3 s · total simple turn ~4 s. The biggest lever is the LLM
behind Hermes; the second is the Whisper model size.

## Gotchas encoded in this repo (learned the hard way)

1. **SSE charset**: Hermes' event stream has no charset header; Python
   `requests` then decodes as Latin-1 → mojibake. The client forces UTF-8.
2. **macOS port 443**: non-root binds only work on the wildcard address
   (`0.0.0.0`), not a specific IP.
3. **launchd + external drives**: see launchd/*.plist comments (TCC hang on
   `getcwd`, EX_CONFIG from external log paths, venv-python invocation).
4. **Browser mic**: requires a secure context — hence the self-signed TLS and
   the per-device cert trust.
5. **ElevenLabs frames** arrive at arbitrary byte boundaries; decode only
   complete int16 pairs and carry the leftover byte.
6. **Near-silent audio** makes faster-whisper raise ("No clip timestamps
   found") — both STT paths treat any transcription exception as an empty
   transcript rather than failing the turn.
7. **Windows venv + NVIDIA pip wheels**: locate the cuBLAS/cuDNN DLLs via
   `sys.prefix` (`site.getsitepackages()` misses the venv) and
   `os.add_dll_directory` them before importing ctranslate2.
8. **Startup**: listeners open immediately; the local Whisper fallback warms
   in the background, exactly once and race-locked (the startup hook fires
   once per uvicorn listener — concurrent recorder inits crash lifespans).
9. **FD limits**: launchd grants 256 file descriptors by default and the
   server idles at ~244 — set NumberOfFiles=8192 in the plist (shipped) and
   close streaming responses in `finally` (done) or it dies within hours.
10. **Orphaned STT children steal ports**: the recorder's child process has a
    cmdline without "server.py", survives naive pkills, and can inherit the
    listen socket — the next spawn then fails its first bind and uvicorn's
    SystemExit cancels ALL listeners. Stop by PORT ownership
    (`lsof -ti tcp:PORT -sTCP:LISTEN | xargs kill -9`) — shipped in
    `scripts/mia-stop.sh`.
11. **Agent tool-choice**: SOUL.md prose cannot redirect the model away from
    attractive built-in tools (it kept "showing" videos in its own invisible
    browser); a first-class plugin tool with an explicit schema wins
    instantly. Hence `hermes-plugin/hud_display`.
