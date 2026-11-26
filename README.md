# MIA — glas in HUD za Hermes Agent

Samostojni glasovni asistent in nadzorni center v stilu Iron Mana, zgrajen na
[Hermes Agent](https://github.com/NousResearch/hermes-agent) (odprtokodni
avtonomni agent podjetja NousResearch). Z *resničnim* agentom se pogovarjaš —
tistim s trajnim spominom, dostopom do terminala, iskanjem po spletu, orodji za
datoteke in 80+ veščinami — prek žarečega HUD-a v katerem koli brskalniku v
tvojem LAN-u ali prek odjemalca za pogovor s pritiskom na tipko.

**Vse teče na tvoji strojni opremi.** Privzeto nič ne zapusti naprave: Whisper
za pretvorbo govora v besedilo, lokalni Piper glas za govor, lokalni model
(llama-server) za Hermesom in lokalni govorniški odtis za prepoznavo tvojega
glasa. Oblačni LLM-ji in ElevenLabs ostajajo opcijski — za nastavitev brez
oblaka ne potrebuješ nobenega ključa.

> English documentation: [README.en.md](README.en.md) · [docs/en/](docs/en/)

## Predstavitev

Izvirni projekt ([eadmin2/jarvis_ai](https://github.com/eadmin2/jarvis_ai)) ima
predstavitveni video; ta različica teče z lokalnim glasovnim pogonom in
slovenskim vmesnikom, zato sta videz in zvok drugačna.

## Kaj dela

**Sam reci »Mia, …«** — ničesar ni treba klikati. HUD se ob odprtju sam vklopi
v neprestano poslušanje; VAD (Silero) razreže govor na izjave, budnica »Mia«
odpre pogovor, konec povedi se zazna sam in odgovor se vrne kot govor, poved
za povedjo, medtem ko se preostanek še generira. Običajen krog s hitrim
lokalnim TTS: 5–10 sekund.

- **Prepoznava govornika (glasovna kalibracija)** — Mia uboga samo tvoj glas:
  ECAPA-TDNN odtis se preveri *pred* transkripcijo (~0,1 s), tuji glasovi in
  televizija se tiho ignorirajo. Vpis z enim ukazom, podprt je večjezični vpis
  (npr. slovenščina + srbščina): `python3 server/scripts/enroll_voice.py`
- **Stroga budnica** — reagira samo na »Mia …« (tolerira tipične Whisperjeve
  variante: Mijo, Mija, Mio, Meja …); hišni hrup se zavrže brez obdelave,
  znane Whisper halucinacije (»Hvala što pratite« …) se filtrirajo
- **Pol-duplex stabilnost** — med obdelavo in govorenjem se ne prekinja (šum
  ne more ubiti turna); ročna prekinitev ostane (gumb STOP / Esc)
- **Drsnik višine glasu** — panel GLAS v HUD-u nastavlja ton od 70 do 240 Hz
  v živo; velja od naslednjega stavka naprej in se trajno shrani
- **Govori slovensko in srbsko** — odgovori v jeziku, v katerem govoriš
- **Odpira in ZAPIRA namizna okna** — »odpri mi Google«, »pusti mi glasbo« …
  in »zapri ga«: pomožni ukazi `mia-open`/`mia-close` (skills/mia-companion/bin)
  si zapisujejo ID oken, zato jih agent zanesljivo zapre; glasba se predvaja v
  namenski Chrome app-oknu (YouTube najde prek `yt-dlp`)
- **Naloge v ozadju** — programiranje v poljubni mapi, datoteke, terminal,
  iskanje po spletu, časovne naloge, kanban; nevarnejša dejanja čakajo na tvoj
  DOVOLI/ZAVRNI v HUD-u
- **Samodejnost (mini pod-OS)** — `mia-auto` zazna stroj in manjkajoča orodja,
  izvaja večkoračne načrte s preverjanjem in rollbackom, vztrajna opravila in
  pravila (»ko bo disk poln …«), zdravstveni nadzor s sanacijo ter deterministične
  sistemske ukaze v slovenščini (datoteke, paketi, omrežje, opomniki)
- **Popoln nadzor nad računalnikom** — `mia-ctl` je revidiran, politiko
  preverjen besednjak za okna, aplikacije, tipkanje/klikanje, posnetke zaslona,
  odložišče, medije, glasnost, svetlost, napajanje, procese, storitve in
  datoteke (X11, Wayland, macOS, Windows). Vsako dejanje gre v revizijo.
- **Kalibracija po oddaljenosti** — Mia ob zagonu zahteva, da ji rečeš nekaj
  od blizu, s sredine sobe in od daleč; shrani ločen glasovni odtis za vsako
  razdaljo in te prepozna kjerkoli v hiši.
- **Stroga budnica** — vsaka izjava se mora začeti z »Mia«; govor, TV, gostje
  in šum se zavržejo že pred prepisom, ko je profil kalibriran.
- **Samo preverjeni uspehi** — recept nastane le iz preverjenega post-conditiona
  (`mia-ctl` `verification.status=verified`) ali iz tvojega ✓ v HUD kartici
  »JE BILO PRAVILNO?«. Nepreverjen uspeh ostane kandidat.
- **Trajen spomin in drevo znanja** — vsak krog se zabeleži v lokalno SQLite
  bazo; iz tega nastanejo navade, recepti in napake, ki se ne smejo ponoviti.
  Pred vsakim krogom se v model vbrizga omejen `[MIA SPOMIN …]` brief.
- **Uči se tvojih postopkov** — ko se izkaže, da je nek postopek pravi, ga Mia
  shrani kot recept in ga ob ponovitvi uporabi; ko rečeš »ni prav«, nastane
  anti-vzorec z vzrokom in rešitvijo.
- **Granularno drevo veščin** — `mia-companion` (persona) + `mia-desktop`,
  `mia-learning`, `mia-music`, `mia-browser`, `mia-productivity`,
  `mia-diagnostics`; validator preveri imena, starše in reference.
- **Seznam zmogljivosti** — ~80 konkretnih sposobnosti (okna, aplikacije, vnos,
  posnetki, odložišče, zvok, zasloni, viri, procesi, storitve, datoteke,
  Google, učenje) s statusi potrjeno/naučeno/zaznano/prazno/nepodprto.
- **Google: poišči-in-povej vs prikaži** — »na Googlu poišči in povej mi«
  odgovori ustno v ozadju; »prikaži mi v Googlu« odpre tvoj brskalnik.
- **HUD NASTAVITVE** — stroga budnica, prag govorca, follow-up, zahtevaj
  profil, preverjanje, učenje, dolžina briefa, kalibracija in sistemski pregled.
- **Aktivnost agenta v živo** — vidiš klice orodij s predogledi ukazov
- **Kartice za odobritev** — nevarne ukaze agent ustavi in počaka na DOVOLI/ZAVRNI
- **Vgrajene nadzorne plošče** — Hermesov kanban, nadzorna plošča in klepet se
  odpreta v animiranih pogledih (POGLEDI) in so polno interaktivni
- **Holografski medijski paneli** — reci *»pokaži … na zaslonu«* in panel
  prileti iz globine; agent to sproži prek priloženega Hermes vtičnika
  (`hud_display`); »počisti zaslon« jih pomete stran
- **Sledenje porabi** — žetoni/dan, izmenjave, vrstica kvote ElevenLabs (če je
  TTS v oblaku)
- **Panel Stroji** — statistika CPU/GPU za gostitelja in oddaljene delavce
- **Filter zasebnosti** — nizi, ki izgledajo kot skrivnosti, se prekrijejo, preden
  besedilo doseže oblačni TTS
- **Opcijska GPU ušesa** — usmeri jo na kateri koli NVIDIA stroj v LAN-u s
  priloženim sidecarjem in prepis skoči na `large-v3-turbo` pri ~0,2 s, z
  samodejnim preklopom na lokalni Whisper, ko je ta stroj ugasnjen
- **Za mobilne naprave** — odzivna postavitev + »Dodaj na začetni zaslon« = Mia
  kot aplikacija čez cel zaslon

## Nadzor računalnika in učenje (na kratko)

```bash
mia-ctl doctor                     # kaj je na tem stroju podprto
mia-ctl windows list               # okna, z ID-ji
mia-ctl apps launch firefox        # zaženi aplikacijo
mia-ctl type "hello" --delay 15    # tipkaj v aktivno okno
mia-ctl screenshot                 # shrani posnetek zaslona
mia-ctl volume set 40              # glasnost
mia-ctl files search "pogodba" --root ~/Documents
mia-ctl power lock                 # zakleni zaslon
```

```bash
mia-learn status                   # koliko spomina, kdaj nazadnje izkopano
mia-learn brief "odpri mi google"  # kaj bi Mia zdaj vedela
mia-learn habits                   # izkopljene navade
mia-learn recipes                  # preverjeni postopki
mia-learn mistakes                 # česa ne ponavljati
mia-learn remember --note "…"      # shrani zadnji postopek
mia-learn feedback --verdict negative --note "raje Chromu"
```

V HUD-u je panel **SPOMIN IN ZNANJE**; gumb **ODPRI ZNANJE** pokaže drevo
veščin, navade, recepte, napake, dnevnik in iskanje. Podrobnosti:
[docs/LEARNING.md](docs/LEARNING.md) in [docs/CONTROL.md](docs/CONTROL.md).

## Samodejnost — mini pod-OS

Mia se zna prilagoditi stroju, načrtovati več korakov, izvajati opravila po
urniku ali ob pogoju ter opaziti in odpraviti težave. Vse gre skozi revidiran
`mia-ctl`, s politiko in potrditvami.

```bash
mia-auto profile                  # kaj je ta stroj, kaj mu manjka
mia-auto adapt                    # predlog namestitve manjkajočih orodij
mia-auto health                   # ocena zdravja + varna sanacija
mia-auto status                   # stroj, zdravje, opravila, naloge
mia-auto do "opomni me čez 10 minut, da pijem vodo"
mia-auto jobs add "jutranji pregled" --daily 08:00 --template health_report
mia-auto tasks list                # dnevnik nalog z nadaljevanjem
mia-auto daemon --interval 30      # urnik brez glasovnega strežnika
```

V HUD-u sta panel **SAMODEJNOST** in stran `/hud/autonomy.html` (pregled,
prilagoditev, opravila in pravila, naloge, ukaz, opozorila). Podrobnosti:
[docs/AUTONOMY.md](docs/AUTONOMY.md).

## 3D lik in garderoba

V sredini HUD-a je zdaj **3D ženski lik** (Ready Player Me kompatibilen GLB z
Mixamo rigom, 72 ARKit/Oculus blendshapi in ločenimi kosi oblačil, las in
očal). Obroč ostane kot holografska podlaga in fallback.

```bash
server/scripts/fetch-avatar-assets.sh        # prenese brezplačni RPM ženski model
./install.sh --yes --open --with-avatar      # isto med namestitvijo
```

- obraz: visemi, čustva, utripanje, pogled, dihanje (brez drugega modela),
- garderoba: zgornji/spodnji del, obutev, očala, lasje (barva/pričeska),
- kamera: doprsni/obraz/cel lik; kakovost: ultra/visoka/varčna,
- sinhronizacija: strežnik pošlje `avatar_speech` z visemi/časi iz vsakega
  stavka TTS; HUD jih veže na `playhead`, brez časovne osi pa na približno
  besedilno oceno.
- HUD stran **LIK IN GARDEROBA** (`/hud/avatar.html`) shrani nastavitve v
  `server/logs/avatar.json`; modeli so v `server/hud/avatar/models/`,
- Avaturn T2 izvoz lahko dodaš kot nov `.glb` in ga izbereš v isti strani;
  T1 demo nima obraznih blendshapov, zato ni privzet.

Podrobnosti, primerjava z MetaHuman/Audio2Face in faze:
[docs/AVATAR.md](docs/AVATAR.md).

## Arhitektura

```
 HUD v brskalniku (katera koli naprava v LAN-u)   Gostitelj (testirano: Linux + systemd; macOS s prilagoditvami)
 ── https/wss :8766 ─────────┐   ┌──────────────────────────────────────┐
   mikrofon · zvočnik · panel├──►│ strežnik glasovnega cevovoda (ta repo)│
                             │   │  VAD + budnica + govorniški odtis    │   ┌──────────────────┐
 Odjemalec za pritisk na tipko│  │  STT: faster-whisper (lokalno)       │   │ llama-server     │
 ── ws :8765 ────────────────┘   │  TTS: lokalni Piper (ali Gepard/Maya1)├──►│ (lokalni LLM)    │
                                 │  HUD + avtentikacija + TLS proxy     │   ├──────────────────┤
                                 └──────────────────────────────────────┘──►│ Hermes Agent     │
                                             │                              │  API :8642 (lo)  │
                                             └── :9443 proxy ──────────────►│  spomin · orodja │
                                                (kanban/plošča/klepet :9119) │  veščine · cron  │
                                                                             └──────────────────┘
```

Eni možgani, več obrazov: glas in tipkani klepet si delita eno trajno Hermes
sejo, zato vsak ve, kaj si rekel drugemu — in spomin preživi vsak ponovni zagon.

**Učenje in nadzor**: vsak sprejet krog se zabeleži v
`~/.local/state/mia/learning.db`; pred naslednjim krogom strežnik vbrizga
omejen brief z navadami, recepti in napakami. `mia-ctl` dejanja gredo skozi
politiko in revizijo (`control-audit.jsonl`), ki se prav tako uči. Drevo veščin
je v `skills/`, pregled v HUD-u pa v panelu **SPOMIN IN ZNANJE**.

**Upravljanje celotnega sklada**: če v `server.yaml` izpolniš sekcijo `stack:`,
`start-mia.sh` po vrsti zbudi llama-server (lokalni model) → Hermes gateway →
Hermes dashboard → TTS storitev → glasovni strežnik (vsak korak se preskoči, če
že teče), `stop-mia.sh` pa vse ustavi v obratnem vrstnem redu in sprosti
RAM/VRAM. Glej `server/config/server.example.yaml`.

## Hiter začetek (en ukaz)

```bash
git clone https://github.com/DanijelTech/Mia.git && cd Mia && ./install.sh --yes --open
```

Ta vrstica klonira repo, namesti pakete v sistemski Python (brez venv), prenese
slovenski glas, ustvari TLS certifikat, doda `MIA_HUD_TOKEN` v `~/.hermes/.env`,
napiše in zažene systemd enoto ter odpre HUD v brskalniku **že prijavljen**
(`?token=` se pretvori v piškotek in odstrani iz naslova).

Če nisi root, dodaj `sudo` — namestitev gre v `pip --user` in `systemctl --user`.
Različice:

```bash
./install.sh --yes --open --with-maya1   # najboljša slovenska izgovorjava
./install.sh --yes --open --with-gepard  # lažji glasovni model za GPU
./install.sh --dry-run                   # najprej poglej, kaj bi naredil
```

Pozneje kadar koli zaženi/odpri znova:

```bash
./start-mia.sh                # zaženi (če je treba), počakaj, odpri HUD
./start-mia.sh --no-open      # samo zaženi in izpiši URL + žeton
./stop-mia.sh                 # ustavi glasovni strežnik (in TTS storitev)
./stop-mia.sh --status        # kaj teče, katera vrata so zasedena
./stop-mia.sh --restart       # ustavi in znova zaženi + odpri
./stop-mia.sh --free-ports    # če vrata ostanejo zasedena, ubij lastnika
./update.sh               # potegni novo izdajo z GitHuba in osveži storitev
./update.sh --check       # samo pokaži, kaj je novega
```

Certifikat je self-signed, zato brskalnik enkrat vpraša — sprejmi.

## Zahteve

- Stroj za strežnik (testirano: Linux + systemd, 2× GPU za lokalni 35B model;
  macOS deluje s prilagoditvami, launchd namesto systemd)
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) nameščen in
  nastavljen z ponudnikom LLM (privzeto lokalni model za llama-server)
- Python 3.11+
- TTS: lokalni **Piper** (privzeto, hiter, brez ključa, popolnoma offline),
  naravnejši **Gepard**, **Maya1** (najboljša slovenska izgovorjava, na CPU
  počasna) ali [ElevenLabs](https://elevenlabs.io) ključ za oblačne glasove —
  lokalna servisa se ob zasedenem GPU samodejno preklopita na CPU/RAM
- Kateri koli sodoben brskalnik v LAN-u
- Opcijsko: `speechbrain` (glasovna kalibracija), `yt-dlp` (YouTube glasba),
  `xdotool` (zanesljivo zapiranje oken), `ffmpeg` (premik višine tona)

## Namestitev

En ukaz, brez venv (namesti se v sistemski Python, tako kot teče Hermes kot root):

```bash
./install.sh                       # sistemsko (root): odvisnosti, glas, cert, žeton, systemd
./install.sh --dry-run             # najprej pokaži vse korake
./install.sh --with-gepard         # + opcijska Gepard TTS storitev
./install.sh --with-maya1          #   ali Maya1 (najboljša izgovorjava)
```

Vse, kar ustvari, zapiše v manifest, zato je odstranitev natančna:

```bash
./uninstall.sh --dry-run      # predogled
./uninstall.sh                # ustavi storitve, odstrani enote, certifikate, glasove, vrstico z žetonom
./uninstall.sh --purge-deps   # ...in pip-odstrani nameščene pakete
```

Za stroj brez interneta: `./build-package.sh` naredi arhiv (z namestitvenimi
skripti, brez glasov), ki ga preneseš in zaženeš z `./install.sh`.

Ročni postopek (in kaj namestitvenik avtomatizira) je v
[docs/SETUP.md](docs/SETUP.md). Kratka različica brez namestitvenika:

```bash
# 1. Vključi API strežnik Hermesa
cat >> ~/.hermes/.env <<EOF
API_SERVER_ENABLED=true
API_SERVER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
MIA_HUD_TOKEN=$(python3 -c 'import secrets;print("mia-"+secrets.token_hex(3))')
EOF
hermes gateway   # ali nastavi njegov LaunchAgent / storitev

# 2. Ta repo
git clone https://github.com/DanijelTech/Mia.git
cd Mia/server
pip install fastapi uvicorn requests pyyaml numpy \
    RealtimeSTT faster-whisper silero-vad websockets psutil
cp config/server.example.yaml config/server.yaml
scripts/make-certs.sh          # self-signed TLS (brskalnik za mikrofon potrebuje HTTPS)
scripts/get-voice.sh sl        # slovenski glas (63 MB)

# 3. Zaženi
python3 server.py
# odpri https://TVOJ_HOST/hud/ → sprejmi certifikat → vnesi MIA_HUD_TOKEN
```

Za samodejni zagon ob bootu glej [launchd/](launchd/) (macOS) oz. systemd enote,
ki jih ustvari `install.sh` — komentarji v plistih opisujejo dve neočitni pasti
macOS-a (TCC pri zunanjih diskih in poti do logov).

## Uporaba

| Dejanje | Kako |
|---|---|
| Pogovor | samo reci **»Mia, …«** — poslušanje, zaznava konca in odgovor so samodejni |
| Prekinitev | rdeč gumb ■ USTAVI ali Esc (med obdelavo/govorjenjem šum ne prekinja) |
| Višina glasu | panel GLAS v HUD-u — drsnik 70–240 Hz, velja od naslednjega stavka |
| Glasovna kalibracija | `python3 server/scripts/enroll_voice.py` (`--append` za dodaten jezik) |
| Glasba | »Mia, pusti mi …« → YouTube app-okno · »zapri ga / ustavi glasbo« |
| Okna na namizju | »odpri mi Google / \<stran\>« in »zapri ga« (mia-open/mia-close) |
| Nadzor računalnika | `mia-ctl …` — okna, aplikacije, vnos, posnetki, odložišče, napajanje |
| Spomin in znanje | panel SPOMIN IN ZNANJE → ODPRI ZNANJE · `mia-learn …` |
| Kalibracija glasu | HUD NASTAVITVE → KALIBRIRAJ · `server/scripts/calibrate_voice.py` |
| Zmogljivosti | panel ZMOGLJIVOSTI → ODPRI SEZNAM · `mia-learn capabilities` |
| Potrditev opravila | HUD kartica »JE BILO PRAVILNO?« ✓/✗ · `mia-learn verify` |
| Google | »poišči in povej« = ustno · »prikaži« = brskalnik |
| Tipkani klepet | vnosno polje na dnu (ista seja kot glas) |
| Kanban / plošče | panel POGLEDI → kanban, nadzorna plošča, klepet |
| Pritisni-in-govori | alternativa: klikni obroč (ali preslednica) · govori · klikni znova |
| Telefon | odpri HUD → Dodaj na začetni zaslon |

## Struktura repozitorija

```
server/          FastAPI glasovni cevovod + gostitelj HUD-a (jedro projekta)
server/hud/      HUD v eni datoteki (vanilla JS, brez gradnje)
server/continuous.py  VAD segmentacija, budnica (wake gate) za neprestano poslušanje
server/speaker_gate.py  prepoznava govornika (ECAPA-TDNN odtisi, SpeechBrain)
server/tts.py    lokalni TTS pogoni: piper, http (Gepard/Maya1), command, elevenlabs
server/mia_core/ učenje in znanje (stdlib-only): SQLite, navade, recepti, napake,
                 drevo veščin, zmogljivosti, kontekstni brief, CLI (mia-learn)
server/mia_core/autonomy/  mini pod-OS: profil stroja, načrti, urnik, pravila,
                 zdravje, deterministični ukazi, CLI (mia-auto)
server/speaker_gate.py  oddaljenostni glasovni odtisi (bližina/sredina/daleč)
server/calibration.py   vodena kalibracija prek HUD WebSocketa
server/hud/settings.html      NASTAVITVE (budnica, prag, učenje, kalibracija)
server/hud/capabilities.html  ZMOGLJIVOSTI (potrjeno/naučeno/prazno)
server/hud/autonomy.html      SAMODEJNOST (profil, načrti, opravila, naloge, zdravje)
server/hud/avatar/      3D lik: Three.js runtime, modeli (fetch), garderoba, visemi
server/avatar_visemes.py  slovenski tekst → Oculus 15 visemov + časovna os
server/scripts/  mia-start/stop/health + enroll_voice.py (glasovna kalibracija)
                 + gepard_tts.py (TTS storitev s per-request višino tona)
client/          opcijski Windows/Linux odjemalec za pritisk na tipko (z zaznavo budnice)
worker/          opcijska GPU sidecarja: STT strežnik z velikim modelom + statistika
hermes-plugin/   Hermes vtičniki: hud_display (medijski paneli), mia_learning
                 (memory_brief/search/feedback/remember/fact/mistake/status/skill_tree)
                 in mia_autonomy (system_status/profile/health/adapt/plans/run_plan/
                 command/jobs/tasks/alerts)
skills/          drevo veščin: mia-companion (koren) + mia-desktop, mia-learning,
                 mia-music, mia-browser, mia-productivity, mia-diagnostics,
                 mia-autonomy
skills/mia-companion/bin/  mia-open, mia-close, mia-volume, mia-artists,
                 mia-learn, mia-skill, mia-ctl (revidiran nadzor računalnika),
                 mia-auto (samodejnost: profil, načrti, urnik, zdravje)
tests/           unittest suite za mia_core, mia-ctl in drevo veščin
launchd/         predloge za samodejni zagon na macOS (pripombe o TCC in FD limitih)
docs/            slovenska dokumentacija: SETUP, ARCHITECTURE, LEARNING, CONTROL,
                 AUTONOMY, AVATAR, CALIBRATION, CAPABILITIES, TROUBLESHOOTING
docs/en/         ista dokumentacija v angleščini
install.sh       namestitev (brez venv, root ali uporabnik) + manifest
start-mia.sh     zbudi cel sklad (stack: llama → Hermes → dashboard → Mia + TTS), odpre HUD
stop-mia.sh      ustavi vse in sprosti RAM/VRAM; status, --restart, --free-ports
update.sh        git pull --ff-only + restart storitve + opozorilo za Ctrl+Shift+R
uninstall.sh     natančna odstranitev vsega, kar je namestil install.sh
build-package.sh arhiv za namestitev na stroju brez interneta
```

## Varnostni model

- Hermesov API ključ nikoli ne doseže brskalnika: HUD komunicira prek strogo
  omejenega proxyja na glasovnem strežniku.
- Vse HUD končne točke + proxy do plošče + brskalniški WebSocketi so zaščiteni z
  žetonom (piškotek, vnesen enkrat na napravo; `start-mia.sh` ga lahko vnese
  samodejno prek `?token=`).
- Hermesov API in plošča poslušata samo na loopbacku.
- Nizi, ki izgledajo kot skrivnosti, se prekrijejo, preden gredo v oblačni TTS.
- `mia-ctl` preveri politiko (`~/.config/mia/control.json`): dovoljene korenine,
  prepovedane poti (`~/.ssh`, `~/.hermes` …), potrditev za uničujoča dejanja.
- Vsako nadzorno dejanje gre v revizijo; skrivnosti v argumentih se prekrijejo.
- Spomin se shranjuje lokalno; vsa besedila se pred shranjevanjem prekrijejo.
- Zasnovano za LAN — tega ne odpiraj na internet.

## Zasluge in licenca

Zgrajeno na [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous
Research). Estetika HUD-a navdihnjena po
[jarvis-dashboard](https://github.com/AndrewKochulab/jarvis-dashboard).
STT: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) /
[RealtimeSTT](https://github.com/KoljaB/RealtimeSTT). Glas: Piper, opcijsko
Gepard / Maya1 (MediaAtlas), opcijsko [ElevenLabs](https://elevenlabs.io).

Izvirno izpeljano iz [eadmin2/jarvis_ai](https://github.com/eadmin2/jarvis_ai)
(MIT, © Chris Lassiter); preimenovano in razširjeno za lokalni slovenski/srbski glas.

MIT — glej [LICENSE](LICENSE). Uporabi, razveji, zgradi svojo Mio.
