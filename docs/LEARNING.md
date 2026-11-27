# Učenje, spomin in drevo znanja

> Angleška različica: [docs/en/LEARNING.md](en/LEARNING.md)

Mia ima trajen, poizvedljiv in razložljiv spomin. Ni to le pogovorna seja v
Hermesu: vsak sprejet krog, vsako dejanje prek `mia-ctl` in vsako uporabnikovo
popravljanje se zapišejo v lokalno bazo, iz katere nastanejo **navade**,
**recepti** in **napake, ki se ne smejo ponoviti**.

Vse teče lokalno. Baza je SQLite v `~/.local/state/mia/learning.db`, audit
nadzornih dejanj pa `~/.local/state/mia/control-audit.jsonl`.

## Krog učenja

```
opazuj → zabeleži → izkoplji → prikliči → deluj → ovrednoti → posodobi
   │         │           │          │         │          │
 glas    epizoda      navade     brief    mia-ctl    odziv uporabnika
 klepet  + orodja     recepti   pred     orodja     »prav / ni prav«
 nadzor  + izid       napake    krogom   Hermes
```

### 1. Samodejno zajemanje

- Vsak **sprejet** glasovni ali tipkani krog se zapiše kot *epizoda*:
  zahteva, odgovor, uporabljena orodja, koraki, izid, trajanje, napake,
  entitete (app, domena, izvajalec, mapa …).
- Vsak klic `mia-ctl` gre v audit JSONL; strežnik ga vsakih ~15 minut uvozi
  kot epizodo z `source=control`.
- Zavrnjeni krog (napačen glas, brez budnice) se **ne** zapiše, da šum ne
  onesnaži spomina.
- Iz uspešne epizode z orodji/koraki nastane **recept**; iz neuspešne
  **anti-vzorec** (napaka + vzrok + rešitev).

### 2. Vbrizganje spomina v vsak krog

Preden zahteva doseže Hermesa, strežnik sestavi omejen blok:

```
[MIA SPOMIN — uporabi to pred dejanjem, ne sprašuj znova]
Navade uporabnika:
- app: google — običajno zjutraj (~07:00) (12×)
Znane nastavitve in dejstva:
- pref.browser: firefox
Preverjeni postopki za to zahtevo:
- odpri google (zaupanje 0.84, 6× uspešno): mia-ctl open https://google.com
Tega NE ponavljaj:
- okno se ne zapre s pkill — vzrok: Chrome posreduje --app okna; rešitev: mia-close
[konec spomina]
```

- Največ `context.max_chars` (privzeto 1500 znakov).
- Če je predolgo, se najprej odrežejo manj pomembni razdelki (veščine).
- Blok je determinističen in razložljiv; ni skritih embeddingov.

### 3. Samo preverjeni uspehi so resnica

Vsaka epizoda ima `verified` in `verification_status`:

- `verified` — `mia-ctl` je preveril post-condition (okno izginilo, glasnost
  se ujema, datoteka obstaja, proces je mrtev, storitev aktivna …),
- `user_confirmed` — uporabnik je kliknil ✓ v HUD kartici ali rekel »tako je«,
- `unverified` — zgleda uspešno, a ni dokazano,
- `user_rejected` / `failed` — uporabnik ali post-condition je rekel ne.

**Recept nastane samo iz `verified` ali `user_confirmed`.** Nepreverjen uspeh
se shrani kot kandidat, ne kot resnica. To je namerno: Mia se uči le iz
preverljivih korakov in se zato vsakič manj moti.

V HUD-u se po opravilu s spremembo prikaže kartica **»JE BILO PRAVILNO?«** z
✓/✗. Kartica je tudi v panelu **ZA POTRDITEV** in na strani ZNANJE → DNEVNIK
(filter »za potrditev«). Ročno:

```bash
mia-learn verify --episode 42 --verdict positive --note "tako je"
mia-learn verify --episode 42 --verdict negative --note "raje Chromu"
```

### 4. Uporabnikov odziv

Kratke fraze strežnik ujame **pred** Hermesom in jih uporabi na zadnji epizodi:

- pohvala: »tako je«, »to je bilo prav«, »pravilno«, »bravo« …
- popravek: »ni prav«, »ne tako«, »narobe«, »naslednjič drugače« …
- ukaz: »zapomni si postopek«, »shrani recept«, »naslednjič naredi tako«

Daljše popravke (npr. »ne tako, raje odpri v Chromu in nastavi glasnost«)
dobi agent; ta mora ukrepati **in** poklicati `mia-learn feedback`.

## Kaj se nauči

### Navade

- **Preferenca**: app, domena, izvajalec, mapa ali poizvedba, ponovljena
  vsaj 3× v 120 dneh.
- **Rutina**: isti subjekt, skoncentriran v 2-urno okno (npr. glasba zvečer),
  če okno vsebuje ≥35 % pojavitev.
- **Zaporedje**: dve nameri, ponovljeni v 20 minutah vsaj 3×
  (npr. glasba → glasnost).
- Zanesljivost raste z dokazi in upada, ko navada preneha (po 45 dneh).

### Recepti

Recept je preverjen postopek z zaupanjem:

```
zaupanje = (uspehi + 1) / (uspehi + neuspehi + 2) × nasičenje
```

- Ujemanje: normalizacija (male črke, brez šumnikov, brez polnilnih besed),
  50 % Jaccard + 30 % pokritost + 20 % podobnost zaporedja.
- Prag 0,52; v brief gredo največ 2 recepta.
- Neuspeh zniža zaupanje in ustvari anti-vzorec.

### Napake (anti-vzorci)

- Kaj je šlo narobe, zakaj in kaj narediti namesto tega.
- Samodejno iz neuspešnih epizod; ročno z `mia-learn mistakes --add`.
- Kasnejši uspeh posodobi rešitev z delujočimi koraki.
- V briefu največ 3 najbolj relevantne.

## Seznam zmogljivosti

Mia ima bogat seznam ~80 zmogljivosti (okna, aplikacije, vnos, posnetki,
odložišče, zvok, zasloni, viri, procesi, storitve, datoteke, brskalnik,
učenje). Vsaka ima status `confirmed` / `learned` / `detected` / `empty` /
`failed` / `unsupported`, ukaz in način preverjanja.

```bash
mia-learn capabilities --refresh
mia-learn capabilities --category desktop
mia-learn capabilities --confirm files.search --notes "testirano"
mia-learn capabilities --fail desktop.input.type --notes "Wayland brez wtype"
```

V HUD-u: panel **ZMOGLJIVOSTI** → **ODPRI SEZNAM**. Podrobnosti:
[CAPABILITIES.md](CAPABILITIES.md).

## Iskanje

`mia-learn search` uporablja SQLite **FTS5** po epizodah, receptih,
anti-vzorcih, dejstvih in navadah. Večbesedne poizvedbe najprej poskusijo `AND`
za natančne zadetke in šele nato `OR`, zato ena odvečna beseda ne poplavi
seznama. `mia-learn mine` in `import` znova indeksirata vse; če je bila baza
ustvarjena pred indeksiranjem dejstev/navad, enkrat zaženi `mia-learn mine`.
Brez FTS5 shramba pade na `LIKE` in še vedno deluje.

## Ukazi

```bash
mia-learn status
mia-learn brief "odpri mi google"
mia-learn episodes --limit 20
mia-learn search "pogodba"
mia-learn habits
mia-learn recipes
mia-learn mistakes
mia-learn facts
mia-learn remember --note "zakaj deluje"
mia-learn feedback --verdict negative --note "raje Chromu"
mia-learn mine
mia-learn sysinfo
mia-learn tree
mia-learn doctor
mia-learn export ~/backups/mia-learning.json
mia-learn import ~/backups/mia-learning.json
mia-learn backup ~/backups/mia-learning.db
mia-learn prune
```

Dodaj `--json` za strojno berljiv izhod.

## Drevo veščin

```
mia-companion        persona, jezik, usmerjanje, varnost
├── mia-desktop      okna, aplikacije, vnos, posnetki, odložišče, napajanje
├── mia-learning     epizode, navade, recepti, napake, povratna zanka
├── mia-music        YouTube, zgodovina, priljubljeni izvajalci
├── mia-browser      iskanje, HUD paneli, brskanje
├── mia-productivity kanban, cron, branje na glas
└── mia-diagnostics  zdravje, dnevnik, ponovni zagon, zmogljivosti
```

Vsaka veščina ima `SKILL.md` s front matter (`name`, `description`,
`parents`, `children`, `tags`, `capabilities`), po potrebi pa še
`references/` in `bin/`.

```bash
mia-skill tree
mia-skill list
mia-skill validate
mia-skill search "okno"
mia-skill install "$HERMES_HOME"
```

Validator preveri unikatna imena, obstoječe starše in obstoječe
`references/` datoteke. `install.sh` namesti celo drevo v aktivni
`$HERMES_HOME/skills`.

## HUD

Panel **SPOMIN IN ZNANJE** prikazuje števce in najmočnejše navade. Gumb
**ODPRI ZNANJE** odpre celotno stran `/hud/learning.html`:

- Pregled (brief, zadnje aktivnosti, top navade/recepti)
- Drevo veščin
- Navade (z dokazi in zaupanjem)
- Recepti (koraki, uspehi/neuspehi)
- Napake (vzrok, rešitev)
- Dnevnik epizod (ročno ✓/✗)
- Iskanje po vsem spominu
- Ročno dodajanje dejstev, napak in receptov

## Konfiguracija

V `server/config/server.yaml`:

```yaml
learning:
  enabled: true
  db_path: "~/.local/state/mia/learning.db"
  audit_path: "~/.local/state/mia/control-audit.jsonl"
  auto_record: true
  auto_feedback: true
  auto_mine_interval_seconds: 900
  context:
    enabled: true
    max_chars: 1500
    max_habits: 6
    max_recipes: 2
    max_mistakes: 3
    max_facts: 5
  verify_prompts: true             # HUD kartica »je bilo pravilno?«
  retention:
    episodes_days: 400
    max_episodes: 200000
  habits:
    min_evidence: 3
    recency_days: 120
    peak_share: 0.35
  recipes:
    match_threshold: 0.52
```

Okoljske spremenljivke: `MIA_LEARNING_ENABLED`, `MIA_LEARNING_DB`,
`MIA_LEARNING_AUDIT`, `MIA_SKILLS_ROOT`, `MIA_LEARNING_CONTEXT_MAX_CHARS`,
`MIA_LEARNING_MINE_INTERVAL`.

## Zasebnost in vzdrževanje

- Vsa besedila se pred shranjevanjem prekrijejo: ključi, žetoni, gesla,
  zasebni ključi, e-pošta, telefonske/cartonaste številke. To je varnostna
  mreža, ne dovoljenje za shranjevanje skrivnosti.
- Retencija: epizode 400 dni / 200 000 vrstic, dogodki 180 dni, stare navade
  se počasi zabrišejo.
- Varnostna kopija: `mia-learn backup` (SQLite) ali `mia-learn export`
  (prenosni JSON).
- Obnovitev: `mia-learn import`.

## Diagnostika

```bash
mia-learn doctor --json
mia-learn stats
mia-learn tree --validate
tail -n 50 ~/.local/state/mia/control-audit.jsonl
```

Če je `last_error` nastavljen, spomin ne deluje, a glasovna zanka teče naprej
— učenje je zasnovano tako, da nikoli ne podre produkcije.

## Omejitve

- Ujemanje receptov je leksikalno, ne semantično; zato so kratki, jasni opisi
  in entitete pomembni.
- Navade potrebujejo vsaj 3 ponovitve; enkratno dejanje ni navada.
- Vgrajeni model mora brief upoštevati; Hermesov sistemski prompt in ta
  drevo veščin sta zato usklajena.
- Brez `mia-ctl` audit poti učenje iz nadzornih dejanj ne deluje, a ročni
  `mia-learn record` še vedno deluje.
