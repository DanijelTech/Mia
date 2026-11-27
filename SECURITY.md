# Security policy

Mia is a **LAN-only, local-first** assistant that can control the machine it
runs on. Treat it like a shell with a microphone: do not expose it to the
public internet.

## Supported versions

Security fixes land on the current `main` and the latest release tag. The
version is in [`VERSION`](VERSION); `/api/version` reports it at runtime.

## Reporting a vulnerability

Please report privately to the repository owner (GitHub security advisory or
the contact in the repository profile). Include:

- Mia version (`./start-mia.sh --version` or `/api/version`),
- OS/desktop and whether the install is system or user mode,
- reproduction steps and the affected endpoint/command,
- whether `MIA_HUD_TOKEN` was set.

Do not open a public issue with an exploit before a fix is available.

## Threat model and guarantees

- **HUD/API auth**: every `/api/*` request, the dashboard proxy and `/ws`
  require `MIA_HUD_TOKEN` when it is configured. The token is accepted as a
  cookie, `X-Mia-Token`/`X-Jarvis-Token` header or `?token=` (the latter is
  converted to a cookie by the HUD). A missing `Origin` does **not** bypass the
  token check.
- **Origins**: browser WebSockets must be same-origin or in
  `security.extra_origin_hosts`.
- **Hermes key**: `API_SERVER_KEY` stays in the Hermes env file; the browser
  never receives it. The HUD uses a strict allowlist proxy.
- **Secrets**: `mia_core/privacy.py` redacts secret-shaped strings before
  storage and before cloud TTS. Never put secrets in prompts, memory or voice.
- **Computer control**: `mia-ctl` checks `~/.config/mia/control.json`
  (allowed roots, denied paths, destructive confirmation). Every action is
  audited in `~/.local/state/mia/control-audit.jsonl`.
- **Plans**: destructive steps require confirmation; nested plans propagate
  their destructive flag; `undo` commands must use the `mia-ctl` vocabulary.
- **Network**: Hermes and the dashboard bind to loopback; the HUD TLS port is
  for the LAN only. Do not port-forward it.
- **Updates**: `update.sh` refuses a dirty tree, fast-forwards only, and tells
  you when `install.sh` must run again. It never overwrites `server.yaml`,
  voices, certificates, logs or the token.

## Hardening checklist

1. Set a strong random `MIA_HUD_TOKEN` (the installer does).
2. Keep `server/config/server.yaml` and `server/certs/` out of version control.
3. Restrict the control policy (`~/.config/mia/control.json`) to the folders
   Mia may touch.
4. Keep `autonomy.allow_destructive` and `auto_install` off unless you really
   want unattended changes.
5. Back up `~/.local/state/mia/learning.db` with `mia-learn backup`.
6. Run `./stop-mia.sh --status` and `mia-ctl doctor` after changing hardware.
