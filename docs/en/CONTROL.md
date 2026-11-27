# Local computer control (`mia-ctl`)

> Slovenian version: [../CONTROL.md](../CONTROL.md)

`mia-ctl` is a small, explicit, audited vocabulary for controlling the local
computer. The agent uses it instead of raw `xdotool`/`wmctrl`/`pkill` because it
provides three guarantees:

1. **Policy** — paths and destructive actions are checked against
   `~/.config/mia/control.json` before anything runs.
2. **Audit** — every call is appended to
   `~/.local/state/mia/control-audit.jsonl` with secrets redacted; the learning
   loop turns it into episodes and habits.
3. **Predictable failure** — unsupported features return exit code 3 with a
   clear reason instead of silently doing nothing.

Exit codes: `0` ok · `2` usage · `3` unsupported · `4` denied · `5` failed.

## Install helpers

```bash
# Debian/Ubuntu X11
sudo apt install xdotool wmctrl xclip scrot playerctl brightnessctl \
                 libnotify-bin wl-clipboard grim
# Wayland
sudo apt install wtype ydotool grim wl-clipboard playerctl brightnessctl
# macOS
brew install cliclick
```

Check what is available:

```bash
mia-ctl doctor --json
mia-learn doctor --json
```

## Commands

```bash
mia-ctl windows list
mia-ctl windows focus "YouTube"
mia-ctl windows close "YouTube"
mia-ctl windows move "Terminal" --x 0 --y 0 --w 1280 --h 720
mia-ctl apps list
mia-ctl apps launch firefox
mia-ctl open https://example.com
mia-ctl type "hello" --delay 15
mia-ctl key ctrl+shift+t
mia-ctl click 640 360
mia-ctl scroll -3
mia-ctl screenshot
mia-ctl clipboard get
mia-ctl clipboard set "text"
mia-ctl notify "Mia" "Task finished"
mia-ctl media play-pause
mia-ctl volume set 40
mia-ctl brightness set 60
mia-ctl power lock
mia-ctl power reboot --yes
mia-ctl process list --limit 15
mia-ctl process kill 12345 --yes
mia-ctl service restart mia-voice --yes
mia-ctl files search "invoice" --root ~/Documents
mia-ctl files recent
mia-ctl files info ~/Documents/invoice.pdf
mia-ctl files mkdir ~/Projects
mia-ctl files copy ~/a.txt ~/b.txt
mia-ctl files move ~/a.txt ~/Projects/ --yes
mia-ctl files rename ~/a.txt ~/b.txt --yes
mia-ctl files trash ~/a.txt --yes          # XDG trash
mia-ctl files delete ~/a.txt --yes         # permanent, needs --yes
mia-ctl files archive ~/Projects ~/projects.zip
mia-ctl files extract ~/projects.zip ~/out
mia-ctl files du ~/Projects
mia-ctl files find-large --min-mb 500
mia-ctl files duplicates --min-mb 1
mia-ctl net status
mia-ctl net wifi list
mia-ctl net wifi connect "Home" "secret"   # password is redacted from audit
mia-ctl net ping 8.8.8.8
mia-ctl net dns
mia-ctl net ports
mia-ctl net firewall status
mia-ctl net firewall enable --yes
mia-ctl pkg manager
mia-ctl pkg search htop
mia-ctl pkg list-upgradable
mia-ctl pkg update --yes
mia-ctl pkg upgrade --yes
mia-ctl pkg install htop --yes
mia-ctl pkg remove htop --yes
mia-ctl sysinfo --json
mia-ctl sys time
mia-ctl sys timezone
mia-ctl sys set-timezone Europe/Ljubljana --yes
mia-ctl sys hostname
mia-ctl sys users
mia-ctl sys locale
mia-ctl sys power-profile
mia-ctl sys failed-services
mia-ctl audit tail --limit 20
mia-ctl policy show
```

`trash`/`delete`/`move`/`rename` require `--yes`; `extract` rejects archive
members that would escape the destination (path traversal).

## Displays, resources, audio

```bash
mia-ctl displays list
mia-ctl resources
mia-ctl audio devices
```

## Verification

Every result carries `verification`:

```json
{"status":"verified","method":"volume_readback",
 "evidence":{"got":40,"expected":40}}
```

`verified` = a real post-condition passed; `failed` = it did not; `unknown` =
no safe post-condition (typing, clicking, power). Only verified actions (or a
user ✓ in the HUD) become trusted recipes.

## Policy

`~/.config/mia/control.json`:

```json
{
  "allowed_roots": ["~", "/tmp", "/var/tmp"],
  "deny_paths": ["~/.ssh", "~/.gnupg", "~/.hermes", "~/.config/mia/secrets"],
  "allow_power": true,
  "allow_process_kill": true,
  "allow_service_control": ["mia-", "hermes-"],
  "allow_package_management": true,
  "allow_network_control": true,
  "allow_file_delete": true,
  "require_confirmation": true,
  "max_text_length": 5000,
  "max_file_scan": 20000,
  "package_timeout": 1800,
  "audit": true,
  "audit_max_mb": 20,
  "autonomy": {
    "allow_destructive": false,
    "auto_install": false,
    "auto_remediate": false
  }
}
```

- `deny_paths` wins over `allowed_roots`.
- `require_confirmation` requires `--yes` for destructive actions.
- `allow_package_management`, `allow_network_control`, `allow_file_delete`
  switch whole families of actions on or off.
- `autonomy.allow_destructive` permits destructive actions without
  confirmation, `auto_install` installs missing tools, and `auto_remediate`
  fixes privileged issues automatically. All three are off by default.
- If policy denies an action, the agent must explain the rule and ask the user
  to change the policy — never bypass it with a shell.

## Audit and learning

Each audit record contains time, action, redacted arguments, success, exit code,
duration, error, host, user, cwd and desktop type.

```bash
mia-ctl audit tail --limit 20
mia-learn mine
```

## Backends

| Feature | Linux X11 | Linux Wayland | macOS | Windows |
|---|---|---|---|---|
| windows | wmctrl | swaymsg / hyprctl | System Events | PowerShell |
| typing | xdotool | wtype / ydotool | osascript | SendKeys |
| mouse | xdotool | ydotool | cliclick | PowerShell |
| screenshot | gnome-screenshot / scrot / import | grim / gnome-screenshot / spectacle | screencapture | PowerShell |
| clipboard | xclip / xsel | wl-clipboard | pbcopy | Set-Clipboard |
| media | playerctl | playerctl | Music | — |
| volume | mia-volume / wpctl / pactl | same | osascript | — |
| brightness | brightnessctl | brightnessctl | brightness | — |

## Safety

- Paths are resolved with `Path.resolve()`; symlinks cannot escape the allowed
  roots.
- Commands are executed as argument lists, never with `shell=True`.
- `type` and `clipboard set` are redacted in the audit log.
- `process kill` refuses PID 1, its own PID and its parent.
- `power` and `service stop/restart` require `--yes`.
- Secrets in arguments are redacted before they reach the audit log.
