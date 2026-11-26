---
name: mia-autonomy
description: "Mia's mini-OS layer: adaptive system profile, multi-step plans, reminders, scheduled jobs, reactive rules, health watchdog and deterministic system commands. Open this for anything about the machine itself beyond a single click."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [Autonomy, System, Scheduling, Health, Adaptation, Plans, Linux]
capabilities: [profile_machine, plan_tasks, schedule_jobs, run_rules, watch_health, adapt_environment, route_system_intents]
metadata:
  hermes:
    tags: [Autonomy, System, Scheduling, Health, Adaptation, Plans, Linux]
---

# Mia autonomy

This skill owns the layer that makes Mia behave like a small operating-system
assistant rather than a chat window: it knows **what machine it is on**, can
**plan several steps**, can **run things later or when a condition becomes
true**, and can **notice and fix problems** — all through audited, policy-checked
primitives.

The CLI is `mia-auto`; the engine is `server/mia_core/autonomy/`; the HUD page
is `/hud/autonomy.html`; the API is `/api/autonomy/*`.

## Core loop

```
detect machine → choose available backends → plan → policy preflight
      → execute steps → verify post-conditions → journal → learn
```

Nothing bypasses `mia-ctl`. A plan is a list of argv lists (never a shell
string). A step is done only when its post-condition holds. Every step is
written to SQLite, so an interrupted task can be inspected or resumed.

## Commands

```bash
mia-auto profile                 # what this machine is + readiness + gaps
mia-auto profile --json
mia-auto adapt                   # show the adaptation plan
mia-auto adapt --apply           # install missing tools (needs policy + root)
mia-auto health                  # scored health report
mia-auto health --remediate      # run the safe fixes
mia-auto status                  # one page: machine, health, jobs, tasks
mia-auto doctor                  # profile + health + ctl + policy

mia-auto plan --list             # available templates
mia-auto plan cleanup            # show a plan as JSON
mia-auto plan cleanup --run --yes
mia-auto do "opomni me čez 10 minut, da pijem vodo"
mia-auto route "preveri posodobitve"   # what would be parsed

mia-auto jobs list
mia-auto jobs add "jutranji pregled" --daily 08:00 --template health_report
mia-auto jobs add "opomnik" --remind 600 --notify "Pij vodo"
mia-auto jobs add "disk" --kind rule --trigger '{"kind":"condition","condition":{"metric":"disk_free_percent","op":"<","value":10},"for_seconds":0}' --template cleanup
mia-auto jobs show 1
mia-auto jobs remove 1

mia-auto tasks list
mia-auto tasks show 12
mia-auto tasks resume 12
mia-auto tasks cancel 12

mia-auto tick                   # one scheduler + health cycle
mia-auto daemon --interval 30   # run the loop without the voice server
```

## Natural language the router already understands

The server handles these **without the LLM** (fast, offline, auditable). Use
the same phrasing when the user speaks:

- resources: »koliko je prostega prostora«, »poraba«, »kateri sistem imaš«
- audio/display: »nastavi glasnost na 40«, »pojačaj«, »utišaj«, »svetlost 60«
- media: »predvajaj«, »pavziraj«, »naslednja pesem«
- windows/apps: »odpri firefox«, »zapri firefox«, »preklopi na terminal«,
  »katera okna so odprta«
- power: »zakleni zaslon«; suspend/reboot/shutdown ask for confirmation
- files: »najdi datoteko X«, »ustvari mapo X«, »kopiraj A v B«,
  »premakni A v B«, »izbriši datoteko X«, »vrzi v smeti X«,
  »stisni X v arhiv.zip«, »razširi arhiv.zip v mapo«, »velikost mape X«
- processes/services: »ustavi proces X«, »ali teče storitev X«,
  »restartaj storitev X«
- network: »kakšno je omrežje«, »katera Wi-Fi omrežja so na voljo«,
  »pingaj 8.8.8.8«, »vklopi požarni zid«
- packages: »preveri posodobitve«, »posodobi sistem«, »namesti paket X«,
  »odstrani paket X«, »poišči paket X«
- time: »opomni me čez 10 minut, da …«, »vsak dan ob 8:00 …«,
  »vsakih 30 minut …«, »ko bo baterija pod 20, me opozori«
- plans: »počisti disk«, »posodobi sistem«, »nočni način«, »delovni način«

If a sentence does not match an anchored command pattern, it goes to the agent.
Do not invent a direct system action for an ambiguous sentence.

## Confirmation protocol

- Destructive actions (power off, process kill, service stop, package install,
  permanent delete, disk cleanup) are persisted as **pending actions**.
- The user must say »ja«/»potrdi«/»izvrši« to execute, or »ne«/»preklici« to
  cancel. A new command supersedes the pending one.
- Policy can make the system stricter, never looser:
  `~/.config/mia/control.json` → `autonomy.allow_destructive`,
  `autonomy.auto_install`, `autonomy.auto_remediate`.
- `require_confirmation: true` is the default. `--yes` is only passed after a
  real confirmation (or by an explicit automation the user created).

## Adaptation (what "autonomous adaptation" means here)

`mia-auto profile` detects OS, distro, init, package manager, desktop
(X11/Wayland/sway/hyprland/GNOME/KDE), audio stack, tools, GPU, battery,
network, privileges and container/VM. It then:

1. selects the first available backend for each capability,
2. scores readiness and lists the missing tools,
3. maps each missing tool to the install command of **this** package manager,
4. records a profile snapshot and the diff (tools added/removed),
5. drives `/api/capabilities` so the HUD checklist matches reality.

`mia-auto adapt --apply` performs step 3 through `mia-ctl pkg install`, but only
when `autonomy.auto_install` is true and the process can elevate. Never claim a
tool works until the post-install profile refresh proves it is present.

## Jobs and rules

- `job` — a clock: `at`, `every`, `daily`.
- `rule` — the machine: `condition` (edge-triggered, optional `for_seconds`),
  `event` (`file_changed`, `service_down`, `battery_low`, `network_down`),
  `idle`.
- A condition rule fires once when it has held long enough and re-arms only
  after the condition clears. This prevents notification storms.
- Jobs are persisted in SQLite with `next_run`; they survive restarts.
- `tick` runs at most `max_jobs_per_tick` jobs (default 3) and never blocks the
  voice loop.

## Health watchdog

Checks: root/home disk, RAM, swap, load, temperature, battery, network, failed
systemd units, TLS certificate expiry, learning DB size, stale tasks, uptime.
Score starts at 100 (warn −8, critical −25). Alerts are deduplicated for one
hour.

Safe remediation (`health --remediate`): stale temp files, learning pruning,
notifications. Privileged/destructive remediation (package cleanup, service
restart) only when `autonomy.auto_remediate` is enabled. Do not remediate a
critical disk by deleting user files — move them to trash or ask.

## Safety rules

1. Never use a shell string. Plans use argv lists.
2. Never store passwords/tokens in a plan, job or recipe. Wi-Fi passwords are
   passed straight to `mia-ctl` and redacted in the audit log.
3. Never remove user data permanently without explicit confirmation; prefer
   the XDG trash.
4. Never install packages silently. State the package list and the manager.
5. Never claim success: read `verification.status`; `unknown` is not success.
6. Learning/autonomy are fail-open: if the DB or profile breaks, the voice loop
   must still answer.

## Troubleshooting

- `mia-auto doctor` first.
- Missing capability → `mia-auto profile` shows the exact package for this
  distro; `mia-auto adapt --apply` installs it when allowed.
- A job did not fire → `mia-auto jobs show ID`, check `next_run`, `last_status`,
  trigger state (`armed`, `since`, `seen`), and the conditions.
- A task is stuck → `mia-auto tasks show ID`; resume after the cause is fixed.
- Health critical → read the check's `remediation`, run `--remediate` only for
  the safe tier, otherwise ask the user.

More concrete recipes: `references/automation-cookbook.md`.
