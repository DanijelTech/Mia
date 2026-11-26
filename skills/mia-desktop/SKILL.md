---
name: mia-desktop
description: "Control the user's local computer: windows, apps, keyboard/mouse input, screenshots, clipboard, notifications, media keys, volume, brightness, power, processes, services and files. Use mia-ctl instead of raw shell commands."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [desktop, windows, apps, input, screenshot, clipboard, power, files]
capabilities: [list_windows, focus_window, close_window, launch_app, type_text, press_keys, click, screenshot, clipboard, notify, media_keys, volume, brightness, power, process_kill, service_control, search_files, open_file]
---

# Mia desktop control

Use this skill whenever the user wants something to happen **on the machine**:
open or close a window, switch apps, type, click, take a screenshot, copy
something, change volume, lock the screen, find a file, check a process.

## Golden rule

Use **`mia-ctl`**, not raw `xdotool`, `wmctrl`, `osascript` or `pkill`.
`mia-ctl` is audited, policy-checked and cross-platform; every call is recorded
and becomes part of Mia's memory. Raw shell bypasses all three.

Exception: if `mia-ctl` returns exit code **3 (unsupported)** because a helper
is missing, you may use the documented fallback, and then tell the user which
package would enable the native path.

## Command table

Run `mia-ctl --help` or `mia-ctl <group> --help` for the full list. Common
commands:

### Windows

```bash
mia-ctl windows list
mia-ctl windows focus "YouTube"          # id, title substring or app name
mia-ctl windows close "YouTube"
mia-ctl windows minimize "Spotify"
mia-ctl windows maximize "Terminal"
mia-ctl windows move "Terminal" --x 0 --y 0 --w 1280 --h 720
```

### Apps

```bash
mia-ctl apps list
mia-ctl apps launch firefox
mia-ctl apps launch "Visual Studio Code"
mia-ctl apps quit firefox
```

### Opening things

```bash
mia-ctl open https://example.com        # uses mia-open when available
mia-ctl open ~/Documents/report.pdf     # default app, path is policy-checked
```

### Keyboard and mouse

```bash
mia-ctl type "hello world" --delay 15
mia-ctl key ctrl+shift+t
mia-ctl key Return
mia-ctl click 640 360 --button 1
mia-ctl move 100 200
mia-ctl scroll -3                        # negative = down
```

### Screen, clipboard, notifications

```bash
mia-ctl screenshot                       # ~/Pictures/mia-YYYYmmdd-HHMMSS.png
mia-ctl screenshot ~/Desktop/shot.png
mia-ctl clipboard get
mia-ctl clipboard set "text"
mia-ctl notify "Mia" "Naloga je končana"
```

### Media, volume, brightness

```bash
mia-ctl media play-pause
mia-ctl media next
mia-ctl media status
mia-ctl volume status
mia-ctl volume set 40
mia-ctl volume up 10
mia-ctl brightness set 60
```

### Power (confirmation required)

```bash
mia-ctl power lock                       # no --yes needed
mia-ctl power suspend --yes
mia-ctl power reboot --yes
mia-ctl power shutdown --yes
```

Always ask aloud before `suspend`, `reboot` or `shutdown` and wait for an
explicit »ja«. Then use `--yes`.

### Processes and services

```bash
mia-ctl process list --limit 15
mia-ctl process find chrome
mia-ctl process kill 12345 --yes
mia-ctl service status mia-voice
mia-ctl service restart mia-voice --yes
```

Only units allowed by `~/.config/mia/control.json`
(`allow_service_control`, default `mia-*` and `hermes-*`) can be controlled.

### Files

```bash
mia-ctl files search "pogodba" --root ~/Documents --limit 20
mia-ctl files recent --limit 15
mia-ctl files open ~/Documents/pogodba.pdf
mia-ctl files reveal ~/Documents/pogodba.pdf
```

Paths are restricted to `allowed_roots` and denied under `deny_paths`
(`~/.ssh`, `~/.hermes`, …). Never try to bypass a denial.

## Safety and confirmations

- **Irreversible** actions (power, kill, service stop/restart) need a spoken
  confirmation and `--yes`.
- **Typing and clicking** affect whatever has focus. If the target matters,
  focus the window first (`mia-ctl windows focus …`) and verify with
  `mia-ctl windows list`.
- **Clipboard and screenshots can contain secrets.** Do not read them aloud,
  do not paste them into cloud services, and do not store them in memory.
- If policy denies an action (exit 4), explain which rule blocked it and ask
  the user to change `~/.config/mia/control.json`. Do not use a shell to
  circumvent it.
- After a failed command (exit 5), read the error, fix the cause, and only then
  retry. Do not repeat the same failing call.

## Backends (what works where)

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

`mia-ctl doctor` prints exactly which tools are present on this machine.

## Learning integration

`mia-ctl` writes an audit line for every call. The voice server ingests it and
turns it into episodes, habits and recipes. You do not need to record the
command again. Do record the *meaning* when it is not obvious:

```bash
mia-learn facts --set "pref.browser" "firefox"
mia-learn facts --set "pref.editor" "code"
mia-learn facts --set "project.current" "Mia"
```

## References

- `references/control-cookbook.md` — ready-made recipes for common requests.
