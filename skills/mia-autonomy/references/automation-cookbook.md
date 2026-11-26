# Automation cookbook

Concrete, testable recipes. Every command here is policy-checked and audited.

## Reminders

```bash
# one shot
mia-auto jobs add "zdravilo" --remind 600 --notify "Vzemi zdravilo"

# every day at 08:00
mia-auto jobs add "jutranji pregled" --daily 08:00 --template health_report

# every 30 minutes
mia-auto jobs add "pošta" --every 1800 --notify "Preveri pošto"
```

Voice equivalents: »opomni me čez 10 minut, da …«, »vsak dan ob 8:00 …«,
»vsakih 30 minut …«.

## Reactive rules

```bash
# disk below 10% → run the cleanup plan
mia-auto jobs add "disk" --kind rule \
  --trigger '{"kind":"condition","condition":{"metric":"disk_free_percent","op":"<","value":10},"for_seconds":0,"poll":60}' \
  --template cleanup

# battery below 20% → notify
mia-auto jobs add "baterija" --kind rule \
  --trigger '{"kind":"condition","condition":{"metric":"battery_percent","op":"<","value":20},"for_seconds":0,"poll":120}' \
  --notify "Baterija je nizka."

# RAM above 90% for five minutes → notify
mia-auto jobs add "ram" --kind rule \
  --trigger '{"kind":"condition","condition":{"metric":"mem_used_percent","op":">","value":90},"for_seconds":300,"poll":60}' \
  --notify "Pomnilnik je poln."

# a file changed → notify
mia-auto jobs add "watch" --kind rule \
  --trigger '{"kind":"event","name":"file_changed","path":"/home/me/Documents/report.md","poll":30}' \
  --notify "Poročilo je bilo spremenjeno."
```

Voice equivalents: »ko bo baterija pod 20, me opozori«,
»ko bo prostor pod 10, počisti disk«.

## Conditions vocabulary

```json
{"metric": "cpu_percent", "op": ">", "value": 90}
{"metric": "mem_used_percent", "op": ">", "value": 85}
{"metric": "disk_free_percent", "op": "<", "value": 10}
{"metric": "battery_percent", "op": "<", "value": 20}
{"metric": "load", "op": ">", "value": 8}
{"metric": "max_temp_c", "op": ">", "value": 85}
{"hour_between": [8, 17]}
{"weekday_in": [0, 1, 2, 3, 4]}
{"file_exists": "/home/me/flag"}
{"file_older_than": {"path": "/home/me/tmp", "seconds": 86400}}
{"service_active": "mia-voice"}
{"wifi_connected": true}
{"on_battery": true}
{"network_up": true}
{"all": [{"metric": "mem_used_percent", "op": ">", "value": 90}, {"hour_between": [0, 6]}]}
{"any": [{"metric": "battery_percent", "op": "<", "value": 10}, {"metric": "disk_free_percent", "op": "<", "value": 5}]}
```

## Plans

```bash
mia-auto plan --list
mia-auto plan health_report
mia-auto plan cleanup --run --yes
```

Built-in templates: `workday`, `cleanup`, `system_update`, `night`,
`health_report`. A plan is JSON:

```json
{
  "name": "moj načrt",
  "destructive": false,
  "steps": [
    {"kind": "ctl", "action": ["volume", "set", "25"],
     "expect": {"json": "percent", "equals": 25}},
    {"kind": "notify", "title": "Mia", "body": "Glasnost je nastavljena."},
    {"kind": "python", "action": "health_check"},
    {"kind": "sleep", "seconds": 2},
    {"kind": "wait_for", "condition": {"service_active": "mia-voice"},
     "wait_timeout": 30, "poll": 2}
  ]
}
```

Allowed step kinds: `ctl`, `python`, `notify`, `speak`, `sleep`, `probe`, `wait_for`,
`plan` (nested). Allowed ctl commands: `windows apps open type key click move
scroll screenshot clipboard notify media volume brightness power process service
files net displays resources audio sysinfo pkg sys audit policy doctor`.

## Health

```bash
mia-auto health
mia-auto health --json
mia-auto health --remediate
```

Critical disk example: the safe tier cleans stale `/tmp` entries older than 48 h
and prunes the learning DB. It never deletes user documents. Move large user
files to the XDG trash instead: `mia-ctl files trash <path> --yes`.

## Adaptation

```bash
mia-auto profile
mia-auto adapt
# enable in ~/.config/mia/control.json:
#   "autonomy": {"auto_install": true}
sudo mia-auto adapt --apply
```

After installing, run `mia-auto profile --refresh`; readiness and
`/api/capabilities` must show the new backend before you rely on it.

## HUD and API

- Page: `/hud/autonomy.html` (tabs: overview, adaptation, jobs, tasks, command,
  alerts).
- `GET /api/autonomy/status`, `/profile`, `/health`, `/jobs`, `/tasks`,
  `/alerts`.
- `POST /api/autonomy/refresh`, `/adapt`, `/remediate`, `/tick`, `/run`, `/text`.
- `POST /api/autonomy/jobs`, `DELETE /api/autonomy/jobs/{id}`,
  `POST /api/autonomy/jobs/{id}/toggle`.
- `POST /api/autonomy/tasks/{id}/resume`, `/cancel`.

The HUD uses the same cookie/token model as the rest of `/api/*`.

## Interrupted work

```bash
mia-auto tasks list
mia-auto tasks show 12
mia-auto tasks resume 12
```

A resume skips steps already marked `done`. Destructive steps still go through
policy; a task created before a policy change does not gain new permissions.
