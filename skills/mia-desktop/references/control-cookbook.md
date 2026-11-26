# Desktop control cookbook

Ready-made sequences for the requests the user makes most often. Adapt names
and paths; never invent flags that `mia-ctl --help` does not list.

## "Odpri mi Google in poišči X"

```bash
mia-open "https://www.google.com/search?q=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "X")"
```

Or, if the page should appear on the HUD instead of the desktop:

```
hud_display(media="iframe", src="https://www.google.com/search?q=...", title="GOOGLE")
```

## "Odpri aplikacijo X"

```bash
mia-ctl apps launch "X"
mia-ctl windows list          # verify it appeared
```

## "Zapri to okno / zapri X"

```bash
mia-ctl windows list
mia-ctl windows close "X"     # or the exact id
```

For windows Mia opened with `mia-open`, prefer `mia-close <domain>` because it
uses the recorded window id.

## "Uredi to datoteko" / "Vpiši to"

```bash
mia-ctl windows focus "Visual Studio Code"
mia-ctl type "..." --delay 15
mia-ctl key ctrl+s
```

If the target window is not obvious, ask one short question before typing.

## "Naredi posnetek zaslona"

```bash
mia-ctl screenshot
# → screenshot: /home/USER/Pictures/mia-20260101-120000.png
```

Tell the user the path; do not read the image contents aloud.

## "Kopiraj to" / "Kaj imam v odložišču?"

```bash
mia-ctl clipboard set "text"
mia-ctl clipboard get
```

Clipboard contents may be secret: summarize instead of reading it aloud.

## "Utišaj / pojačaj / glasnost na 30"

```bash
mia-ctl volume mute
mia-ctl volume set 30
mia-ctl volume up 10
```

The deterministic voice path also handles simple volume phrases without you.

## "Predvajaj / pavziraj glasbo"

```bash
mia-ctl media play-pause
mia-ctl media status
```

For YouTube specifically, use the **mia-music** skill; `mia-ctl media` only
controls MPRIS players.

## "Najdi datoteko X"

```bash
mia-ctl files search "X" --root ~/Documents --limit 20
```

If nothing is found, widen the root once (`~`), then report honestly. Do not
scan the whole disk repeatedly.

## "Zakleni zaslon"

```bash
mia-ctl power lock
```

## "Ugasi računalnik"

1. Ask aloud: »Naj ugasnem računalnik?«
2. Wait for an explicit yes.
3. `mia-ctl power shutdown --yes`

## "Kaj troši CPU?"

```bash
mia-ctl process list --limit 15
mia-ctl sysinfo --json
```

## "Ali Mia teče?"

```bash
mia-ctl service status mia-voice
mia-ctl service status mia-tts
mia-ctl doctor
```

## Failure playbook

| Exit | Meaning | What to do |
|---|---|---|
| 3 | Unsupported / helper missing | report which package enables it; use the documented fallback once |
| 4 | Denied by policy | explain the rule; ask the user to edit `~/.config/mia/control.json` |
| 5 | Command failed | read stderr, fix the cause, retry once, then report |
