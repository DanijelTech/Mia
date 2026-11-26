---
name: mia-diagnostics
description: "Diagnose and recover the Mia stack: health checks, logs, service status, capability detection, learning-store health and safe restarts. Use when something does not work, before claiming a feature is broken, or when the user asks 'why'."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [diagnostics, health, logs, systemd, recovery, capabilities]
capabilities: [health_check, read_logs, check_capabilities, restart_service, inspect_learning_store]
---

# Mia diagnostics

## First response: measure, do not guess

Run the cheap checks first, in this order:

```bash
mia-ctl doctor --json            # desktop backend + tools + policy + audit
mia-learn doctor --json          # learning DB + skill tree + tools
mia-learn status                 # memory counts, last mining, last error
mia-ctl service status mia-voice
mia-ctl service status mia-tts
server/scripts/mia-health.sh     # stack health (Hermes, TTS, voice)
```

Also check the new surfaces:

```bash
mia-learn capabilities --refresh      # what this machine can actually do
mia-ctl displays list                 # monitors and resolutions
mia-ctl resources                     # CPU/RAM/disk/GPU + top processes
mia-ctl audio devices                 # sinks and sources
```

The HUD **NASTAVITVE** page controls strict wake, the speaker threshold, the
require-profile switch, verification cards, learning and the memory-brief
length. The **ZMOGLJIVOSTI** page is the confirmed/learned/empty checklist.

Then read only the relevant log:

```bash
journalctl --user -u mia-voice -n 80 --no-pager
journalctl --user -u mia-tts -n 80 --no-pager
tail -n 50 server/logs/latency.jsonl
tail -n 50 ~/.local/state/mia/control-audit.jsonl
```

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| »Hermesov gateway ni dosegljiv« | gateway not running / wrong key | `hermes gateway`, check `API_SERVER_KEY` in `~/.hermes/.env`, `systemctl --user restart mia-voice` |
| HUD shows 401 | missing/expired cookie | open the HUD with `?token=$MIA_HUD_TOKEN` once |
| Voice does not wake | speaker gate, mic, VAD | `mia-ctl doctor`; check `server/logs/`, re-enroll voice |
| Windows do not close | plain Chrome/pkill path | use `mia-close <domain>`; verify `mia-ctl windows list` |
| `mia-ctl` exits 3 | helper missing | install the package named in the error (xdotool, wmctrl, grim, …) |
| `mia-ctl` exits 4 | policy denial | edit `~/.config/mia/control.json`, do not bypass with shell |
| Memory empty | learning disabled / DB unwritable | `mia-learn status`; check `learning.enabled` and `~/.local/state/mia` permissions |
| Recipes never appear | nothing is verified yet | confirm HUD ✓/✗ cards; `mia-learn capabilities --refresh` |
| Mia ignores you | strict wake or speaker profile | check **NASTAVITVE**; calibrate; say »Mia, …« |
| Wrong voice accepted | threshold too low / no profile | calibrate distance profile, raise threshold |
| Recipes never match | too few episodes / threshold | `mia-learn mine`; inspect `mia-learn brief "…"` |
| Skill tree errors | missing reference/parent | `mia-skill validate`, fix the reported file |

## Restarts

```bash
mia-ctl service restart mia-voice --yes
mia-ctl service restart mia-tts --yes
./stop-mia.sh --status
./stop-mia.sh --restart
```

Never restart the voice server in the middle of a turn unless the user asked.
After a restart, tell the user to hard-refresh the HUD (`Ctrl+Shift+R`) if the
frontend changed.

## Capability claims

Before saying »to ne morem«, prove it:

```bash
mia-ctl doctor --json | jq '.data.features'
mia-ctl windows list
mia-ctl screenshot
```

If a feature is unsupported, name the missing package and the exact command
that would enable it. Do not silently fall back to a destructive shell command.

## Learning-store health

```bash
mia-learn doctor --json
mia-learn stats
mia-learn tree --validate
mia-learn prune
mia-learn backup ~/backups/mia-learning.db
```

The store is designed to fail open: a broken DB must never take the voice loop
down. If `last_error` is set, report it and keep the conversation working.

## Escalation

If the same failure survives two different fixes:

1. Stop retrying.
2. Summarize what was tried and the exact error.
3. Offer the user a safe next step (restart, reinstall, check hardware).
4. Record the anti-pattern: `mia-learn mistakes --add … --cause … --fix …`.
