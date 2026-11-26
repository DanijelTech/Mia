# Capability checklist (confirmed / learned / empty)

Mia keeps a machine-checked inventory of what she can do on **this** computer.
Every item has an id, category, label, command, detection method and status.

## Statuses

| Status | Meaning |
|---|---|
| `confirmed` | the user confirmed it works |
| `learned` | Mia used it successfully (audit) |
| `detected` | the backend is present but not used yet |
| `empty` | not checked / empty field |
| `failed` | last use/check failed |
| `unsupported` | no backend on this machine, with a hint |

Only `confirmed` and `learned` are treated as reliable.

## Categories (~80 items)

voice, audio, display, desktop (windows/apps/input/screenshot/clipboard/
notifications/media/power), system (resources/CPU/RAM/disk/GPU/battery/
network/displays/audio devices/processes/services), files, browser (open URL,
Google answer/show, HUD), knowledge (memory/habits/recipes/mistakes/skills/
verification/plugin), security (policy/audit/redaction).

## HUD

Panel **ZMOGLJIVOSTI** → **ODPRI SEZNAM** (`/hud/capabilities.html`):
search, category/status filters, ✓ confirm, ✗ fail, · clear, free-text notes,
and **OSVEŽI DETEKCIJO**.

## CLI

```bash
mia-learn capabilities
mia-learn capabilities --refresh
mia-learn capabilities --category desktop
mia-learn capabilities --status empty
mia-learn capabilities --confirm files.search --notes "tested"
mia-learn capabilities --fail desktop.input.type --notes "Wayland without wtype"
mia-learn capabilities --json
```

## API

```
GET  /api/capabilities?refresh=1&category=&status=&query=
POST /api/capabilities/refresh
POST /api/capabilities/confirm   {"id":"files.search","status":"confirmed","notes":"..."}
```

## Verified learning

`mia-ctl` returns a `verification` object: `verified`, `failed` or `unknown`,
with a method and evidence. Only verified actions (or a user ✓ in the HUD)
become recipes. Unverified successes are candidates, not truth.

The audit loop marks a capability `learned` when its action succeeds; a user
confirmation is never overwritten by auto-detection.
