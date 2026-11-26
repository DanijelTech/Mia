# Popoln nadzor nad lokalnim računalnikom (`mia-ctl`)

`mia-ctl` je majhen, ekspliciten in revidiran besednjak za upravljanje
računalnika. Agent ga uporablja namesto surovih `xdotool`/`wmctrl`/`pkill`
ukazov, ker prinaša tri garancije:

1. **Politika** — poti in uničujoča dejanja se preverijo pred izvedbo
   (`~/.config/mia/control.json`).
2. **Revizija** — vsak klic gre v
   `~/.local/state/mia/control-audit.jsonl` (skrivnosti prekrite), od koder
   ga učenje spremeni v epizode in navade.
3. **Predvidljiv neuspeh** — če funkcija ni podprta, vrne kodo 3 z jasnim
   razlogom, namesto da tiho ne naredi nič.

Izhodne kode: `0` uspeh · `2` uporaba · `3` nepodprto · `4` zavrnjeno ·
`5` napaka.

## Namestitev

`install.sh` namesti `mia-ctl` v `~/.local/bin` (ali `/usr/local/bin` kot
root) in ustvari privzeto politiko. Za polne zmogljivosti namesti še
sistemske pripomočke:

```bash
# Debian/Ubuntu (X11)
sudo apt install xdotool wmctrl xclip scrot playerctl brightnessctl \
                 libnotify-bin wl-clipboard grim

# Wayland (Sway/Hyprland)
sudo apt install wtype ydotool grim wl-clipboard playerctl brightnessctl

# macOS
brew install cliclick
```

Preveri, kaj imaš:

```bash
mia-ctl doctor --json
mia-learn doctor --json
```

## Ukazi

### Okna

```bash
mia-ctl windows list
mia-ctl windows focus "YouTube"
mia-ctl windows close "YouTube"
mia-ctl windows minimize "Spotify"
mia-ctl windows maximize "Terminal"
mia-ctl windows restore "Terminal"
mia-ctl windows move "Terminal" --x 0 --y 0 --w 1280 --h 720
```

Podprti backend-i: X11 (`wmctrl`), Sway (`swaymsg`), Hyprland (`hyprctl`),
macOS (System Events), Windows (PowerShell).

### Aplikacije

```bash
mia-ctl apps list
mia-ctl apps launch firefox
mia-ctl apps quit firefox
```

### Odpiranje

```bash
mia-ctl open https://example.com     # prek mia-open, če je na voljo
mia-ctl open ~/Documents/report.pdf  # privzeta aplikacija, pot preverjena
```

### Tipkovnica in miška

```bash
mia-ctl type "hello" --delay 15
mia-ctl key ctrl+shift+t
mia-ctl click 640 360
mia-ctl move 100 200
mia-ctl scroll -3
```

### Zaslon, odložišče, obvestila

```bash
mia-ctl screenshot
mia-ctl screenshot ~/Desktop/shot.png
mia-ctl clipboard get
mia-ctl clipboard set "text"
mia-ctl notify "Mia" "Naloga je končana"
```

### Mediji, glasnost, svetlost

```bash
mia-ctl media play-pause
mia-ctl media status
mia-ctl volume status
mia-ctl volume set 40
mia-ctl brightness set 60
```

### Napajanje

```bash
mia-ctl power lock
mia-ctl power suspend --yes
mia-ctl power reboot --yes
mia-ctl power shutdown --yes
```

Brez `--yes` se `suspend`, `reboot` in `shutdown` zavrnejo (koda 4).

### Procesi in storitve

```bash
mia-ctl process list --limit 15
mia-ctl process find chrome
mia-ctl process kill 12345 --yes
mia-ctl service status mia-voice
mia-ctl service restart mia-voice --yes
```

Dovoljene so le storitve iz `allow_service_control` (privzeto `mia-*`,
`hermes-*`).

### Datoteke

```bash
mia-ctl files search "pogodba" --root ~/Documents --limit 20
mia-ctl files recent --limit 15
mia-ctl files info ~/Documents/pogodba.pdf
mia-ctl files open ~/Documents/pogodba.pdf
mia-ctl files reveal ~/Documents/pogodba.pdf
mia-ctl files mkdir ~/Projekti
mia-ctl files copy ~/a.txt ~/b.txt
mia-ctl files move ~/a.txt ~/Projekti/ --yes
mia-ctl files rename ~/a.txt ~/b.txt --yes
mia-ctl files trash ~/a.txt --yes          # XDG koš, ne trajno
mia-ctl files delete ~/a.txt --yes         # trajno, le z --yes
mia-ctl files archive ~/Projekti ~/projekti.zip
mia-ctl files extract ~/projekti.zip ~/izhod
mia-ctl files du ~/Projekti
mia-ctl files find-large --min-mb 500
mia-ctl files duplicates --min-mb 1
```

Iskanje je omejeno na `allowed_roots` in nikoli ne vstopa v `deny_paths`
(`~/.ssh`, `~/.hermes`, …). `trash`/`delete`/`move`/`rename` zahtevajo `--yes`;
`extract` zavrne člane, ki bi ušli ciljni mapi (path traversal).

### Zasloni, viri, zvok

```bash
mia-ctl displays list        # monitorji, ločljivosti, fokus
mia-ctl resources            # CPU/RAM/disk/GPU + najbolj obremenjeni procesi
mia-ctl audio devices        # izhodne in vhodne zvočne naprave
```

### Preverjanje uspeha

Vsak rezultat vsebuje `verification`:

```json
{"status":"verified","method":"volume_readback",
 "evidence":{"got":40,"expected":40}}
```

- `verified` — post-condition je uspel (okno izginilo, glasnost se ujema,
  datoteka obstaja, proces mrtev, storitev aktivna …).
- `failed` — post-condition ni uspel.
- `unknown` — varnega post-conditiona ni (tipkanje, klikanje, napajanje).

Samo `verified` dejanja (ali uporabnikovo ✓) postanejo zaupanja vredni
recepti. Podrobnosti: [CAPABILITIES.md](CAPABILITIES.md).

### Omrežje

```bash
mia-ctl net status
mia-ctl net wifi list
mia-ctl net wifi connect "Domače" "geslo"     # geslo se v reviziji prekrije
mia-ctl net wifi disconnect
mia-ctl net ping 8.8.8.8 --count 4
mia-ctl net dns
mia-ctl net ports
mia-ctl net firewall status
mia-ctl net firewall enable --yes
```

### Paketi

```bash
mia-ctl pkg manager                    # apt/dnf/pacman/zypper/apk/brew
mia-ctl pkg search htop
mia-ctl pkg info htop
mia-ctl pkg list-upgradable
mia-ctl pkg update --yes
mia-ctl pkg upgrade --yes
mia-ctl pkg install htop --yes
mia-ctl pkg remove htop --yes
```

### Sistem

```bash
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
mia-ctl policy check ~/Documents
```

## Politika

`~/.config/mia/control.json` (ustvari ga `install.sh` iz
`server/config/control.example.json`):

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

- `allowed_roots` in `deny_paths` se razrešita na absolutne poti; `deny_paths`
  ima prednost.
- `require_confirmation` zahteva `--yes` za uničujoča dejanja.
- `allow_package_management`, `allow_network_control`, `allow_file_delete`
  vklopijo/izklopijo celotne družine dejanj.
- `autonomy.allow_destructive` dovoli nevarna dejanja brez potrditve,
  `auto_install` samodejno namestitev manjkajočih orodij, `auto_remediate`
  samodejno sanacijo privilegiranih težav. Privzeto vse izklopljeno.
- `audit_max_mb` ob preseženju obrne datoteko v `.1`.
- Če politika zavrne dejanje, agent **ne sme** obiti z lupino; mora razložiti
  pravilo in predlagati spremembo.

## Revizija in učenje

Vsak zapis vsebuje: čas, dejanje, argumente (prekrite), uspeh, kodo, trajanje,
napako, gostitelja, uporabnika, delovno mapo in vrsto namizja.

```bash
mia-ctl audit tail --limit 20
mia-learn mine              # uvozi audit v epizode in izkoplje navade
```

Tako `mia-ctl windows close "YouTube"` postane dokaz za navado in morebitni
recept, ne pa le nepregleden stranski učinek.

## Backend-i

| Funkcija | Linux X11 | Linux Wayland | macOS | Windows |
|---|---|---|---|---|
| okna | wmctrl | swaymsg / hyprctl | System Events | PowerShell |
| tipkanje | xdotool | wtype / ydotool | osascript | SendKeys |
| miška | xdotool | ydotool | cliclick | PowerShell |
| posnetek | gnome-screenshot / scrot / import | grim / gnome-screenshot / spectacle | screencapture | PowerShell |
| odložišče | xclip / xsel | wl-clipboard | pbcopy | Set-Clipboard |
| mediji | playerctl | playerctl | Music | — |
| glasnost | mia-volume / wpctl / pactl | isto | osascript | — |
| svetlost | brightnessctl | brightnessctl | brightness | — |

## Varnost

- Poti se razrešijo s `Path.resolve()` (simbolične povezave se ne morejo
  izviti iz dovoljenih korenin).
- Ukazi se izvajajo kot seznam argumentov, nikoli prek `shell=True`.
- `type` in `clipboard set` sta v reviziji prekrita; vsebina se ne shranjuje.
- `process kill` zavrne PID 1, lastni PID in starša.
- `power` in `service stop/restart` zahtevata `--yes`.
- Skrivnosti v argumentih se pred revizijo prekrijejo.

## Razširitev

Novo skupino dodaj v `build_parser()` in `dispatch()` v
`skills/mia-companion/bin/mia-ctl`. Drži se pravil:

1. Preveri politiko (`resolve_path`, `require_yes`).
2. Uporabi `sh([...])` z seznamom argumentov.
3. Vrni slovar z rezultatom; `_summarize()` naj ga zna prikazati.
4. Dodaj test v `tests/test_mia_ctl.py` (headless okolje).
