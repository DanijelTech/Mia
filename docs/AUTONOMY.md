# Samodejnost — mini pod-OS

> Angleška različica: [en/AUTONOMY.md](en/AUTONOMY.md)

Mia ni več samo glasovni vmesnik: plast `server/mia_core/autonomy/` poskrbi, da
se zna **prilagoditi stroju**, **načrtovati več korakov**, **izvajati stvari
pozneje ali ob pogoju** in **opaziti ter odpraviti težave** — vse prek
revidiranih, politiko preverjenih ukazov.

```
zaznaj stroj → izberi razpoložljive backende → načrt → politika
      → izvedi korake → preveri post-condition → dnevnik → učenje
```

Nič ne obide `mia-ctl`. Načrt je seznam argumentnih seznamov, nikoli shell
niz. Korak je opravljen šele, ko velja njegov post-condition. Vsak korak se
zapiše v SQLite, zato je prekinjena naloga vidna in jo je mogoče nadaljevati.

## Sestavni deli

| Modul | Naloga |
|---|---|
| `autonomy/profile.py` | zaznava OS, distro, init, paketni upravitelj, namizje, avdio, orodja, GPU, baterijo, omrežje, privilegije, container; izbere backend in izračuna pripravljenost |
| `autonomy/conditions.py` | deklarativni pogoji (metrike, ure, datoteke, storitve, Wi-Fi, baterija) brez `eval` |
| `autonomy/planner.py` | načrti, preflight politike, izvajanje, preverjanje, retry, rollback, dnevnik, nadaljevanje |
| `autonomy/scheduler.py` | `at`/`every`/`daily`/`condition`/`event`/`idle` opravila in pravila, vztrajna v SQLite |
| `autonomy/health.py` | zdravstvene preverbe, ocena, opozorila, varna sanacija |
| `autonomy/intents.py` | deterministični slovenski/angleški router sistemskih ukazov |
| `autonomy/service.py` | skupna fasada za strežnik, HUD in CLI |
| `autonomy/cli.py` | `mia-auto` ukazi |

## Prilagajanje stroju

`mia-auto profile` požene zaznavo in pokaže:

- sistem, jedro, arhitekturo, namizni strežnik (X11, Wayland, sway, hyprland),
- init (systemd, openrc, launchd), paketni upravitelj (apt, dnf, pacman,
  zypper, apk, brew),
- razpoložljiva orodja in izbrani backend za vsako zmogljivost,
- pripravljenost v odstotkih in manjkajoča orodja z **imenom paketa za ta
  distribucijo**,
- razliko od prejšnjega snapshota (dodana/odstranjena orodja).

`mia-auto adapt --apply` namesti manjkajoče pakete prek `mia-ctl pkg install`,
a le če je v politiki `autonomy.auto_install` res in ima proces pravice.
Po namestitvi se profil osveži; zmogljivost šteje šele, ko je backend res
prisoten.

## Načrti

Koraki: `ctl`, `python`, `notify`, `speak`, `sleep`, `probe`, `wait_for`, `plan`.
Vsak `ctl` korak ima lahko:

- `expect` — `{"exit": 0}`, `{"json": "pot", "equals": ...}`,
  `{"stdout_contains": "..."}`,
- `retries` in `timeout`,
- `on_fail` (`abort`/`continue`),
- `undo` — ukaz za rollback v obratnem vrstnem redu,
- `require_verified` — `verification.status` iz `mia-ctl` mora biti `verified`.

Vgrajeni načrti: `workday`, `cleanup`, `system_update`, `night`,
`health_report`. Poglej jih z `mia-auto plan --list` in
`mia-auto plan cleanup`.

## Opravila in pravila

- `job` — ura: `at`, `every`, `daily`.
- `rule` — stroj: `condition` (edge-triggered, `for_seconds`), `event`
  (`file_changed`, `service_down`, `battery_low`, `network_down`), `idle`.

Pogojno pravilo se sproži enkrat, ko pogoj dovolj dolgo velja, in se znova
oboroži šele, ko pogoj mine. To prepreči plaz obvestil. Opravila preživijo
ponovni zagon, ker so v SQLite z `next_run`.

`tick` izvede največ `max_jobs_per_tick` opravil (privzeto 3) in ne blokira
glasovne zanke. Strežnik požene `tick` vsakih `autonomy.interval_seconds`
(privzeto 30 s); na strežniku brez glasu lahko teče `mia-auto daemon`.

## Zdravje

Preverbe: korenski in domači disk, RAM, swap, load, temperatura, baterija,
omrežje, neuspele systemd enote, potek TLS certifikata, velikost učne baze,
zagozdene naloge, čas delovanja. Ocena se začne pri 100 (warn −8, critical
−25). Opozorila se deduplicirajo za eno uro.

Varna sanacija: stare temp datoteke, pruning učne baze, obvestila. Privilegirana
ali uničujoča sanacija (paketi, storitve) le ob `autonomy.auto_remediate`.
Kritičnega diska Mia ne rešuje z brisanjem uporabnikovih datotek — premakne jih
v XDG koš ali vpraša.

## Naravni govor

Router ujame ukaze pred Hermesom, ko se stavek začne z glagolom ali vsebuje
nedvoumno sistemsko frazo. Primeri:

```
Mia, nastavi glasnost na 40
Mia, zakleni zaslon
Mia, odpri firefox
Mia, najdi datoteko invoice
Mia, ustvari mapo Projekti
Mia, kopiraj datoteko a.txt v b.txt
Mia, vrzi v smeti a.txt
Mia, stisni Dokumenti v arhiv.zip
Mia, ali teče storitev mia-voice
Mia, pingaj 8.8.8.8
Mia, preveri posodobitve
Mia, namesti paket htop
Mia, opomni me čez 10 minut, da pijem vodo
Mia, vsak dan ob 8:00 mi povej dobro jutro
Mia, ko bo baterija pod 20, me opozori
Mia, počisti disk
Mia, posodobi sistem
```

Če stavek ne ustreza nobenemu sidranemu vzorcu, gre do agenta. Router ne
ugiba pri dvoumnih stavkih.

## Potrditve

Nevarna dejanja (ugasni, spanje, ponovni zagon, ustavitev procesa/storitve,
namestitev/odstranitev paketa, trajno brisanje, čiščenje diska) se shranijo kot
**čakajoča dejanja** (`pending_actions`). Uporabnik reče »ja«/»potrdi«/»izvrši«
ali »ne«/»preklici«. Novo povelje nadomesti čakajoče. Politika lahko zahteva
strožje obnašanje, nikoli blažjega.

## CLI

```bash
mia-auto profile [--refresh] [--json]
mia-auto adapt [--apply]
mia-auto health [--remediate] [--json]
mia-auto status
mia-auto doctor
mia-auto route "preveri posodobitve"
mia-auto do "opomni me čez 10 minut, da pijem vodo"
mia-auto plan --list
mia-auto plan cleanup [--run --yes]
mia-auto jobs list|add|show|remove|enable|disable
mia-auto tasks list|show|resume|cancel
mia-auto tick
mia-auto daemon --interval 30
```

## API in HUD

- `GET /api/autonomy/status`, `/profile`, `/plans`, `/health`, `/jobs`, `/tasks`,
  `/alerts`
- `POST /api/autonomy/refresh`, `/adapt`, `/remediate`, `/tick`, `/run`,
  `/text`
- `POST /api/autonomy/jobs`, `DELETE /api/autonomy/jobs/{id}`,
  `POST /api/autonomy/jobs/{id}/toggle`
- `POST /api/autonomy/tasks/{id}/resume`, `/cancel`

Hermes vtičnik `mia_autonomy` izpostavi iste operacije kot prvorazredna orodja (`system_status`, `system_run_plan`, `system_job_add`, …).

HUD stran `/hud/autonomy.html` ima zavihke: pregled, prilagoditev, opravila in
pravila, naloge, ukaz, opozorila. Panel **SAMODEJNOST** na glavnem HUD-u kaže
pripravljenost, zdravje in število opravil.

## Politika in varnost

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

- `allow_destructive` — nevarna dejanja brez potrditve (privzeto izklopljeno),
- `auto_install` — samodejna namestitev manjkajočih orodij,
- `auto_remediate` — samodejna sanacija privilegiranih težav.

Gesla se nikoli ne shranjujejo v načrt, opravilo ali recept. Wi-Fi geslo gre
neposredno v `mia-ctl`, revizija pa ga prekrije. Brisanje gre privzeto v XDG koš.

## Testi

```bash
python3 -m unittest tests.test_autonomy -v
python3 -m unittest discover -s tests -v
```

Testi pokrijejo profil, metrike, načrte, potrditve, retry, rollback, dnevnik,
pogojna pravila (edge-triggered), dogodke, zdravje, opozorila, router in CLI.
