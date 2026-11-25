# Troubleshooting

> Slovenian version: [../TROUBLESHOOTING.md](../TROUBLESHOOTING.md)

> Renamed from `jarvis_ai`: the server still accepts the old `JARVIS_HUD_TOKEN` env var, the `jarvis_token` cookie and `X-Jarvis-Token` header, so an upgrade cannot silently disable auth.


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
systemctl --user restart mia-voice && ./start.sh
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

If Hermes runs as **root** and Mia as a normal user (or vice versa), the key is in
the other user's env file and Mia cannot read it — copy it over or run both as the
same user.

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
