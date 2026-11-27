# Troubleshooting

> Slovenian version: [../TROUBLESHOOTING.md](../TROUBLESHOOTING.md)

> Renamed from `jarvis_ai`: the server still accepts the old `JARVIS_HUD_TOKEN` env var, the `jarvis_token` cookie and `X-Jarvis-Token` header, so an upgrade cannot silently disable auth.


**HUD shows `HTTPConnectionPool(... port=8642): Connection refused` / Mia says
"Hermes gateway unreachable"** — either the gateway is not running or its
environment lacks `API_SERVER_ENABLED`/`API_SERVER_KEY`. **Editing `.env` does not
affect an already running process** — always `hermes gateway restart` afterwards.
Check:

```bash
grep -nE '^API_SERVER' ~/.hermes/.env          # are the lines really there
hermes gateway restart
curl -s -m 2 http://127.0.0.1:8642/health      # {"status":"ok",...}
grep -i "api server" ~/.hermes/logs/gateway.log | tail -3
```

If nothing listens after the restart either, start the gateway with an explicit
environment (bypasses any `.env` loading):

```bash
hermes gateway stop
API_SERVER_ENABLED=true API_SERVER_PORT=8642 \
API_SERVER_KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2) \
hermes gateway
```

The old entry follows: the Hermes gateway is not running (often because
it was started in a terminal that got closed). Run it persistently:

```bash
hermes gateway install --start-now --start-on-login   # Hermes' own service manager
hermes gateway status                                 # running? (PID)
hermes gateway list                                   # profiles
tail -n 40 ~/.hermes/logs/gateway.log                 # look for "API Server"
```

If the log says `API Server: aiohttp not installed`, the gateway silently skips the
platform: `python3 -m pip install --user aiohttp` and `hermes gateway restart`.

If `status --deep` does not mention `api_server`, the gateway does not see
`API_SERVER_ENABLED`/`API_SERVER_KEY` in its environment (profiles have their own
`.env`). Temporarily: `nohup hermes gateway >> ~/.hermes/gateway.log 2>&1 &`.

Verify: `curl -s -H "Authorization: Bearer $(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)" http://127.0.0.1:8642/health`

**In STALNO mode nothing happens after I stop talking** — first look at the label
under the brain: `SLIŠIM …` means the server hears you, `POSLUŠAM` means silence.
Three steps:

1. **Space** (or clicking the brain) while listening submits the current utterance
   immediately (`flush`) — always works, even when end-of-speech is missed;
2. if `SLIŠIM` never appears, the server does not hear you: check
   `stt.continuous` in `server.yaml`, try `threshold: 0.3`, `min_rms: 150`;
3. if `SLIŠIM` never returns to `POSLUŠAM`, raise `silence_ms` to 1000 and
   `end_threshold` to 0.3, or keep `energy_override: true` (default).

The `status` message on start tells which VAD runs (`silero` or `rms`); `rms`
means Silero was unavailable and detection is energy-based (coarser).

**Mia's memory / system tools are missing in Hermes** — `plugin.yaml` declares
the tools, but Hermes only sees them when the plugin's `register(ctx)` runs. An
older build shipped empty `hermes-plugin/mia_learning/__init__.py` and
`hermes-plugin/mia_autonomy/__init__.py`; update and re-enable:

```bash
cd ~/Mia && git pull
ls -l hermes-plugin/mia_learning/__init__.py   # must not be 0 bytes
hermes plugins list | grep -E 'mia_learning|mia_autonomy'
hermes plugins enable mia_learning mia_autonomy
systemctl --user restart mia-voice
```

Then ask the agent to call `memory_status` or `system_status`; a JSON answer
proves registration. `tests/test_plugin_registration.py` fails if a declared
tool is not registered.

**The HUD is in English but Mia still speaks Slovenian** — the deterministic
replies (clock, weather, media, volume, autonomy) follow `MIA_LANG`, which
`/api/ui/language` sets when you press ENG. Check the server log for
`UI language -> en`; if it is missing, the request did not reach the server
(open the HUD from the same origin, or `curl -X POST /api/ui/language`). The
LLM itself needs `hermes.language_directive_en` (or the built-in English
directive) — the Slovenian directive is skipped in English mode. Restart after
editing `server.yaml`.

**The first word takes too long / she is silent for 20 s** — the reply is
streamed: each TTS chunk is sent as the engine produces it, and a long clause
is cut at `tts.max_chunk_chars` (default 220). If the first audio still waits,
the TTS engine itself is slow (CPU Piper on a busy box, or Maya1 loading) —
check `[tts]` lines and `/health` on :8770. For a slow agent, set
`hermes.ack_after_seconds: 3` so she says "Right away." instead of silence.

**She cuts me off / does not interrupt** — `stt.continuous.silence_ms` is the
ceiling for the adaptive endpoint (350–700 ms). A short command closes at
`min_silence_ms`, a long sentence at `silence_ms`. To interrupt by voice, set
`barge_in: true`; barge-in now waits for a completed utterance of at least
`barge_min_ms` and, with a calibrated voiceprint, does not require the wake
word. Without a profile the strict wake word stays mandatory.

**Whisper repeats the same sentence / invents text on silence** — keep
`stt.condition_on_previous_text: false` (default) and
`stt.no_speech_threshold: 0.6`. The `hallucination_filter` list catches known
phrases; add your own if a new one appears. Never put the wake word in
`initial_prompt`.

**HUD says "voice server unreachable" / "connection refused (4401)"** — the
browser opened the WebSocket with an Origin that was not allowlisted. Opening the
HUD by LAN IP (`https://192.168.1.10:8766/hud/`) sends
`Origin: https://192.168.1.10:8766`; older builds only allowed `mia.local`,
`localhost` and `127.0.0.1`. Current code **always allows same-origin** (same
host as the HUD) and still rejects foreign sites. After updating:

```bash
cd ~/Mia && git pull && systemctl --user restart mia-voice
# then Ctrl+Shift+R in the browser
```

If 4401 persists, the token does not match — open
`https://<lan-ip>:8766/hud/?token=$(grep '^MIA_HUD_TOKEN=' ~/.hermes/.env | cut -d= -f2)`.

**Gateway log shows `GET /v1/skills failed … TypeError: find_all_skills() got an
unexpected keyword argument 'include_editorial'`** — this is a **bug in Hermes
itself** (release v0.23.4 / tag v2026.9.24, and still on `main`):
`gateway/platforms/api_server.py` calls `find_all_skills(…, include_editorial=True)`
while `tools/skills_tool.py` only accepts `skip_disabled`. So `/v1/skills` returns
500 and the HUD SKILLS panel shows `—`. Voice and chat keep working.

Minimal local patch (one line, with a backup):

```bash
cd /path/to/hermes-agent-src
cp tools/skills_tool.py tools/skills_tool.py.bak.$(date +%Y%m%d-%H%M%S)
python3 - <<'PY'
import pathlib
p = pathlib.Path("tools/skills_tool.py")
s = p.read_text()
old = "def find_all_skills(*, skip_disabled: bool = False)"
new = "def find_all_skills(*, skip_disabled: bool = False, include_editorial: bool = False)"
if old not in s:
    print("pattern not found — already patched?"); raise SystemExit(1)
p.write_text(s.replace(old, new, 1)); print("patched:", p)
PY
hermes gateway restart
sleep 10
curl -s -H "Authorization: Bearer $(grep '^API_SERVER_KEY=' $HOME/.hermes/.env | cut -d= -f2-)" "http://127.0.0.1:8642/v1/skills" | head -c 200
```

A Hermes update will overwrite the patch — re-check whether upstream fixed it and
re-apply if needed. The older description (checkout vs runtime) only applies if
your error text differs from this one:` — this is not Mia: its proxy
just forwards the call. Hermes runs from a **source checkout**
(`…/hermes-agent-src`) while the imported `agent`/`skills` library comes from a
different installed version. Make both come from the same tree:

```bash
cd /path/to/hermes-agent-src

# 1) on a detached tag `git pull` fails — pick a tag or a branch first:
git status -sb | head -2            # "not currently on a branch" = detached HEAD
git fetch --tags
git tag --sort=-v:refname | head -3
git switch --detach <tag>           # or: git switch main && git pull

# 2) let Hermes prepare its own isolated runtime; no pip needed:
hermes gateway restart              # prints "Preparing the isolated Hermes runtime… ✓"

# 3) PEP 668 blocks `pip install -e .`; only if you insist on the system Python:
python3 -m pip install -e . --break-system-packages   # not recommended
```

Until then the HUD shows `—` and "ni dosegljivo (Hermes)" in SKILLS.

**Gateway log shows `Local session … receipt refused: ValueError: stored identity
mismatch at _checked_entry:119`** — at startup Hermes restores old local sessions
and **refuses + skips** any whose stored identity (profile/user/route) does not
match the current one. They are warnings, not failures: new sessions are created
fresh and work. They appear after moving `~/.hermes` (another home, another disk,
e.g. `/media/…/hermes-home`) or changing the profile identity. Nothing needs
deleting; for a clean slate back up `~/.hermes` and prune the old session store.

**HUD shows "Hermes API offline", SKILLS "?", AUTOMATIONS "—", CPU/memory "—"** —
all of that comes from Hermes **through Mia's proxy** (`/api/hermes/...`), so it
needs (1) `API_SERVER_KEY` in the env file of the user running Mia and (2)
`hermes gateway` on `127.0.0.1:8642`. Check both:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
TOK=$(grep '^MIA_HUD_TOKEN=' ~/.hermes/.env | cut -d= -f2)
curl -s -H "X-Mia-Token: $TOK" http://127.0.0.1:8765/api/hermes/health/detailed | head -c 200
```

The DIAGNOSTICS panel now says `offline — ključ?` (key) or `offline — gateway?`
so you can tell the two apart.

**My LLM launcher refuses to start: "GPU already used by another process, pid …
/usr/bin/python3"** — that is **Mia's voice server** holding Whisper on the GPU
(~2.4 GB). Keep Whisper on CPU when the LLM shares the card:

```bash
cd ~/Mia && ./install.sh --stt-device cpu
systemctl --user restart mia-voice
nvidia-smi          # Mia's python3 should be gone
```

Then start the LLM. The reverse (GPU STT) only makes sense if the LLM is loaded
first and there is VRAM to spare.

**Install completes but `mia-health.sh` shows everything DOWN** — nearly always
`faster-whisper` and `silero-vad` missing (RealtimeSTT treats them as optional
extras but fails at runtime without them), or the server cannot bind its ports.
Check the log with `journalctl --user-unit mia-voice -n 40 --no-pager` (or
`sudo journalctl` for a system unit), then re-run `./install.sh --yes` — it
installs the missing packages and fixes `tls_ports`. A failing listener no
longer takes the others down (previously a failed :443 bind killed :8765 too).

**The service dies with `status=218/CAPABILITIES`** — the unit contains
`AmbientCapabilities=CAP_NET_BIND_SERVICE`, which a **user** unit cannot get;
systemd exits before Python even runs. Older installer builds wrote that line;
current ones do not. Fix:

```bash
cd ~/Mia && git pull && ./install.sh --yes     # rewrites the unit without capabilities
systemctl --user restart mia-voice && ./start-mia.sh
```

**Log shows `PermissionError` / `SystemExit(1)` on port 443** — you are not root.
Set `tls_ports: [8766]` in `server/config/server.yaml` and open
`https://<lan-ip>:8766/hud/`.

**Mia stops working after you log out** — user systemd units stop with the last
session: `loginctl enable-linger $USER`.

**`pip --user` upgraded shared packages (e.g. `websockets` 15 → 16)** —
RealtimeSTT pins `websockets==16` and user `site-packages` is shared with other
software (e.g. `gradio-client` wants `<16`). Mia works; give the other app its own
environment if it breaks.

**HUD loads but mic is blocked** — you're on plain http or an untrusted cert.
Browsers require a secure context for `getUserMedia`. Trust `certs/cert.pem`
on the device (see SETUP §3) and use `https://`.

**First connection after server start times out** — the Whisper model warms at
startup (~40 s). `scripts/mia-health.sh` until all rows are OK.

**"Agent backend offline. Running in basic mode."** — the Hermes API server is
unreachable **or** Mia cannot see the key. Check `API_SERVER_ENABLED` /
`API_SERVER_KEY` in the env file of the user that runs Mia, and that
`hermes gateway` is running:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
```

If the key is not there at all, enable the API server and create one:

```bash
grep -q '^API_SERVER_ENABLED=' ~/.hermes/.env || echo 'API_SERVER_ENABLED=true' >> ~/.hermes/.env
grep -q '^API_SERVER_KEY=' ~/.hermes/.env || \
  echo "API_SERVER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" >> ~/.hermes/.env
systemctl --user restart mia-voice        # Mia reads the env at startup
hermes gateway                            # the gateway must re-read it too
```

If Hermes runs as **a different user** (e.g. root) than Mia, the key in
`/root/.hermes/.env` is not visible to you — copy it over or run both as the same
user. When Hermes is installed in your own home, it is the same file
(`~/.hermes/.env`) and nothing needs copying.

**Transcripts are wrong/garbled words** — make sure you're on the current HUD
(hard refresh): mic must capture at 16 kHz natively. Upgrading `stt.model` to
`small.en` helps. Loud rooms: get closer to the mic; echo cancellation is on.

**Replies show â€™ / â€œ style garbage** — you're running an old server.py;
current code forces UTF-8 on the Hermes SSE stream.

**401 everywhere / ACCESS CODE loop** — the token you entered doesn't match
`MIA_HUD_TOKEN` in `~/.hermes/.env`. Clear the `mia_token` cookie and
retry; restart the voice server after changing the env var.

**LaunchAgent exits with EX_CONFIG** — your log paths point at an external
volume. Keep `StandardOutPath`/`StandardErrorPath` on the internal disk.

**LaunchAgent "running" but nothing listens, log empty** — TCC is blocking the
process from your external drive: it hangs inside `getcwd()`/`open()`. Grant
Full Disk Access to `Python.app` inside your Python framework (see the plist
comments), and invoke the **venv** python directly — no `bash -c 'cd ...'`
wrapper.

**Port 443 "address already in use" or permission denied** — bind `0.0.0.0`
(macOS only exempts wildcard binds for non-root low ports) and make sure a
previous instance fully released the port before restarting.

**ElevenLabs quota shows "chars today" instead of a quota bar** — give your
API key the User → Read permission in the ElevenLabs dashboard.

**Stop button says stopped but Hermes kept working briefly** — on Hermes
v0.16, session runs aren't registered in the runs store (`/stop` 404s); the
halt works by dropping the SSE stream. Newer Hermes builds may fix this.

**"No clip timestamps found. Set 'vad_filter'..." error** — old build; current
code treats silent/unintelligible audio as an empty transcript on both the
local and GPU STT paths.

**GPU STT: "Library cublas64_12.dll is not found"** — the NVIDIA pip wheels
aren't on the DLL search path. Use the shipped `worker/stt_server.py` (it
resolves them via `sys.prefix`) and install `nvidia-cublas-cu12
nvidia-cudnn-cu12` into the same venv.

**HUD unreachable for ~15 s after a restart** — normal: launchd's respawn
throttle. If it lasts longer, run `scripts/mia-health.sh` on the host.

**HTTPS dead but the plain ws port still answers** — two known causes, both
fixed in current files but worth knowing: (1) file-descriptor exhaustion
(launchd default is 256; the shipped plist raises it to 8192), and (2) an
orphaned STT child process holding a port from a previous run, which makes the
next spawn fail its first bind and silently cancel all the TLS listeners. Use
`scripts/mia-stop.sh` — it kills by port ownership — never a bare pkill.

**Slow page loads from Windows (10s+), instant by IP** — Windows mDNS is
flaky with `.local` names. Add a hosts-file entry (admin):
`<server-ip> mia.local mia` (give the server a DHCP reservation first).

**Agent replies are empty (content null, 0 input tokens)** — your LLM
provider is out of quota/credits, not a bug here. Check the Hermes gateway
log for 429/402 errors and configure a `fallback_providers` entry in Hermes'
config.yaml.

**Agent "shows" things in its own browser instead of the HUD** — install and
enable the bundled `hermes-plugin/hud_display` (see SETUP). Prose
instructions don't beat tool schemas; the plugin does.

**Phone can't reach mia.local** — some Android versions lack mDNS; use the
raw IP (and add it to `security.extra_origin_hosts` in server.yaml so the
WebSocket origin check accepts it).
