# Autonomy — a mini sub-OS layer

> Slovenian original: [../AUTONOMY.md](../AUTONOMY.md)

Mia is no longer only a voice interface: `server/mia_core/autonomy/` lets her
**adapt to the machine**, **plan several steps**, **run work later or when a
condition becomes true**, and **notice and fix problems** — all through audited,
policy-checked primitives.

```
detect machine → choose available backends → plan → policy
      → execute steps → verify post-conditions → journal → learn
```

Nothing bypasses `mia-ctl`. A plan is a list of argv lists, never a shell
string. A step is done only when its post-condition holds. Every step is
written to SQLite, so an interrupted task is visible and resumable.

## Components

| Module | Responsibility |
|---|---|
| `autonomy/profile.py` | detect OS, distro, init, package manager, desktop, audio, tools, GPU, battery, network, privileges, container; select backends and score readiness |
| `autonomy/conditions.py` | declarative conditions (metrics, time, files, services, Wi-Fi, battery) with no `eval` |
| `autonomy/planner.py` | plans, policy preflight, execution, verification, retries, rollback, journal, resume |
| `autonomy/scheduler.py` | `at`/`every`/`daily`/`condition`/`event`/`idle` jobs and rules persisted in SQLite |
| `autonomy/health.py` | health checks, score, alerts, safe remediation |
| `autonomy/intents.py` | deterministic Slovenian/English system command router |
| `autonomy/service.py` | shared facade for the server, HUD and CLI |
| `autonomy/cli.py` | `mia-auto` commands |

## Adapting to the machine

`mia-auto profile` reports:

- OS, kernel, architecture, desktop (X11, Wayland, sway, hyprland),
- init (systemd, openrc, launchd), package manager (apt, dnf, pacman, zypper,
  apk, brew),
- available tools and the selected backend per capability,
- a readiness percentage and missing tools with **the package name for this
  distribution**,
- the diff against the previous snapshot (tools added/removed).

`mia-auto adapt --apply` installs the missing packages through
`mia-ctl pkg install`, but only when `autonomy.auto_install` is true and the
process can elevate. After installation the profile is refreshed; a capability
counts only when the backend is actually present.

## Plans

Step kinds: `ctl`, `python`, `notify`, `speak`, `sleep`, `probe`, `wait_for`, `plan`.
A `ctl` step may carry:

- `expect` — `{"exit": 0}`, `{"json": "path", "equals": ...}`,
  `{"stdout_contains": "..."}`,
- `retries` and `timeout`,
- `on_fail` (`abort`/`continue`),
- `undo` — a rollback command executed in reverse order,
- `require_verified` — `mia-ctl` `verification.status` must be `verified`.

Built-in templates: `workday`, `cleanup`, `system_update`, `night`,
`health_report`. Inspect them with `mia-auto plan --list` and
`mia-auto plan cleanup`.

## Jobs and rules

- `job` — a clock: `at`, `every`, `daily`.
- `rule` — the machine: `condition` (edge-triggered, `for_seconds`), `event`
  (`file_changed`, `service_down`, `battery_low`, `network_down`), `idle`.

A condition rule fires once when the condition has held long enough and
re-arms only after it clears. This prevents notification storms. Jobs survive
restarts because they live in SQLite with `next_run`.

`tick` runs at most `max_jobs_per_tick` jobs (default 3) and never blocks the
voice loop. The server ticks every `autonomy.interval_seconds` (default 30 s);
a headless box can run `mia-auto daemon`.

## Health

Checks: root/home disk, RAM, swap, load, temperature, battery, network, failed
systemd units, TLS certificate expiry, learning DB size, stale tasks, uptime.
The score starts at 100 (warn −8, critical −25). Alerts are deduplicated for an
hour.

Safe remediation: stale temp files, learning pruning, notifications.
Privileged/destructive remediation (packages, services) only when
`autonomy.auto_remediate` is enabled. Mia never fixes a full disk by deleting
user documents — she moves them to the XDG trash or asks.

## Natural language

The router catches commands before Hermes when a sentence starts with a verb or
contains an unambiguous system phrase:

```
Mia, set volume to 40
Mia, lock the screen
Mia, open firefox
Mia, find the file invoice
Mia, create a folder Projekti
Mia, copy file a.txt to b.txt
Mia, move a.txt to trash
Mia, compress Documents into arhiv.zip
Mia, is service mia-voice running
Mia, ping 8.8.8.8
Mia, check for updates
Mia, install package htop
Mia, remind me in 10 minutes to drink water
Mia, every day at 8:00 say good morning
Mia, when the battery drops below 20, warn me
Mia, clean up disk
Mia, update the system
```

If the sentence matches no anchored pattern, it goes to the agent. The router
does not guess on ambiguous sentences.

## Confirmations

Destructive actions (shutdown, suspend, reboot, process/service stop, package
install/remove, permanent delete, disk cleanup) are stored as **pending
actions** (`pending_actions`). The user says “yes”/“confirm”/“do it” or
“no”/“cancel”. A new command supersedes the pending one. Policy can make the
system stricter, never looser.

## CLI

```bash
mia-auto profile [--refresh] [--json]
mia-auto adapt [--apply]
mia-auto health [--remediate] [--json]
mia-auto status
mia-auto doctor
mia-auto route "check for updates"
mia-auto do "remind me in 10 minutes to drink water"
mia-auto plan --list
mia-auto plan cleanup [--run --yes]
mia-auto jobs list|add|show|remove|enable|disable
mia-auto tasks list|show|resume|cancel
mia-auto tick
mia-auto daemon --interval 30
```

## API and HUD

- `GET /api/autonomy/status`, `/profile`, `/plans`, `/health`, `/jobs`, `/tasks`,
  `/alerts`
- `POST /api/autonomy/refresh`, `/adapt`, `/remediate`, `/tick`, `/run`,
  `/text`
- `POST /api/autonomy/jobs`, `DELETE /api/autonomy/jobs/{id}`,
  `POST /api/autonomy/jobs/{id}/toggle`
- `POST /api/autonomy/tasks/{id}/resume`, `/cancel`

The `mia_autonomy` Hermes plugin exposes the same operations as first-class tools (`system_status`, `system_run_plan`, `system_job_add`, …).

The HUD page `/hud/autonomy.html` has tabs: overview, adaptation, jobs and
rules, tasks, command, alerts. The **SAMODEJNOST** panel on the main HUD shows
readiness, health and job counts.

## Policy and safety

`~/.config/mia/control.json`:

```json
{
  "allow_package_management": true,
  "allow_network_control": true,
  "allow_file_delete": true,
  "autonomy": {
    "allow_destructive": false,
    "auto_install": false,
    "auto_remediate": false
  }
}
```

- `allow_destructive` — destructive actions without confirmation (off),
- `auto_install` — install missing tools automatically,
- `auto_remediate` — automatic remediation of privileged issues.

Passwords are never stored in a plan, job or recipe. A Wi-Fi password goes
straight to `mia-ctl` and is redacted from the audit log. Deletion defaults to
the XDG trash.

## Tests

```bash
python3 -m unittest tests.test_autonomy -v
python3 -m unittest discover -s tests -v
```

The tests cover the profile, metrics, plans, confirmations, retries, rollback,
journal, edge-triggered rules, events, health, alerts, the router and the CLI.
