# MIA — glas in HUD za Hermes Agent

Samostojni glasovni asistent in nadzorni center v stilu Iron Mana, zgrajen na
[Hermes Agent](https://github.com/NousResearch/hermes-agent) (odprtokodni
avtonomni agent podjetja NousResearch). Z *resničnim* agentom se pogovarjaš —
tistim s trajnim spominom, dostopom do terminala, iskanjem po spletu, orodji za
datoteke in 80+ veščinami — prek žarečega HUD-a v katerem koli brskalniku v
tvojem LAN-u ali prek odjemalca za pogovor s pritiskom na tipko.

**Vse teče na tvoji strojni opremi.** Privzeto nič ne zapusti naprave: Whisper
za pretvorbo govora v besedilo, lokalni Piper glas za govor in tvoj model za
Hermesom. Oblačni LLM-ji in ElevenLabs ostajajo opcijski — za nastavitev brez
oblaka ne potrebuješ nobenega ključa.

> English documentation: [README.en.md](README.en.md) · [docs/en/](docs/en/)

## Predstavitev

Izvirni projekt ([eadmin2/jarvis_ai](https://github.com/eadmin2/jarvis_ai)) ima
predstavitveni video; ta različica teče z lokalnim glasovnim pogonom in
slovenskim vmesnikom, zato sta videz in zvok drugačna.

## Kaj dela

Klikni obroč in govori. Besede se **sproti prepisujejo na zaslon**, medtem ko
govoriš. Prepis gre do Hermesa, ki *res nekaj naredi* — bere in piše datoteke,
izvaja ukaze, išče po spletu, si te zapomni med sejami — odgovor pa se vrača kot
govor, poved za povedjo, medtem ko se preostanek še generira. Običajen krog:
3–5 sekund.

HUD okoli obroča je pravi nadzorni center:

- **Aktivnost agenta v živo** — vidiš klice orodij s predogledi ukazov
- **Gumb STOP** — ustavi ušel krog agenta sredi klica orodja (deluje tudi Esc)
- **Kartice za odobritev** — nevarne ukaze agent ustavi in počaka na DOVOLI/ZAVRNI
- **Prekinjanje med govorom (barge-in)** — prekini ga sredi povedi; ve natančno,
  kaj si slišal in česa ne
- **Vgrajene nadzorne plošče** — Hermesov kanban in brskalnik sej se odpreta v
  animiranih pogledih in sta polno interaktivna
- **Holografski medijski paneli** — reci *»pokaži mi video o tem, kako delujejo
  ark reaktorji, na zaslonu«* in panel prileti iz globine, izriše okvir, se
  materializira skozi skenirno linijo in predvaja video. Agent to sproži prek
  priloženega Hermes vtičnika (`hud_display`); paneli lahko pristanejo levo/desno,
  »počisti zaslon« pa jih pomete stran
- **Sledenje porabi** — žetoni/dan, izmenjave, vrstica kvote ElevenLabs (če je
  TTS v oblaku)
- **Panel Stroji** — statistika CPU/GPU za gostitelja in oddaljene delavce
- **Kinematični zagon** — pritisni `B`: paneli utripnejo, obroč se zavrti,
  »Sistemi so na voljo. Dobro jutro.«
- **Filter zasebnosti** — nizi, ki izgledajo kot skrivnosti, se prekrijejo, preden
  besedilo doseže oblačni TTS
- **Opcijska GPU ušesa** — usmeri jo na kateri koli NVIDIA stroj v LAN-u s
  priloženim sidecarjem in prepis skoči na `large-v3-turbo` pri ~0,2 s, z
  samodejnim preklopom na lokalni Whisper, ko je ta stroj ugasnjen
- **Za mobilne naprave** — odzivna postavitev + »Dodaj na začetni zaslon« = Mia
  kot aplikacija čez cel zaslon

## Arhitektura

```
 HUD v brskalniku (katera koli naprava v LAN-u)   Gostitelj (testirano: macOS / Apple Silicon)
 ── https/wss :443 ──────────┐   ┌──────────────────────────────────────┐
   mikrofon · zvočnik · panel├──►│ strežnik glasovnega cevovoda (ta repo)│
                             │   │  STT: faster-whisper (lokalno)       │   ┌─────────────────┐
 Odjemalec za pritisk na tipko│  │  TTS: lokalni Piper (ali Gepard/Maya1)├──►│ Hermes Agent    │
 ── ws :8765 ────────────────┘   │  HUD + avtentikacija + TLS proxy     │   │  API :8642 (lo) │
                                 └──────────────────────────────────────┘   │  spomin · orodja│
                                                                             │  veščine · cron │
                                                                             └─────────────────┘
```

Eni možgani, več obrazov: glas in tipkani klepet si delita eno trajno Hermes
sejo, zato vsak ve, kaj si rekel drugemu — in spomin preživi vsak ponovni zagon.

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
./start.sh                # zaženi (če je treba), počakaj, odpri HUD
./start.sh --no-open      # samo zaženi in izpiši URL + žeton
./stop.sh                 # ustavi glasovni strežnik (in TTS storitev)
./stop.sh --status        # kaj teče, katera vrata so zasedena
./stop.sh --restart       # ustavi in znova zaženi + odpri
./stop.sh --free-ports    # če vrata ostanejo zasedena, ubij lastnika
```

Certifikat je self-signed, zato brskalnik enkrat vpraša — sprejmi.

## Zahteve

- Stroj za strežnik (testirano: Mac mini, Apple Silicon; Linux deluje s
  prilagoditvami, systemd namesto launchd)
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) nameščen in
  nastavljen z ponudnikom LLM
- Python 3.11+
- TTS: lokalni **Piper** (privzeto, brez ključa, popolnoma offline), naravnejši
  **Gepard**, **Maya1** (najboljša slovenska izgovorjava) ali
  [ElevenLabs](https://elevenlabs.io) ključ za oblačne glasove — lokalna
  servisa se ob zasedenem GPU samodejno preklopita na CPU/RAM
- Kateri koli sodoben brskalnik v LAN-u

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
| Pogovor | klikni obroč (ali preslednica) · govori · klikni znova za pošiljanje |
| Ustavi agenta | rdeč gumb ■ USTAVI ali Esc |
| Prekini med govorom | klikni obroč, medtem ko govori |
| Tipkani klepet | vnosno polje na dnu (ista seja kot glas) |
| Kinematični zagon | pritisni `B` |
| Kanban / plošče | panel POGLEDI → animirani pogledi |
| Telefon | odpri HUD → Dodaj na začetni zaslon |

## Struktura repozitorija

```
server/          FastAPI glasovni cevovod + gostitelj HUD-a (jedro projekta)
server/hud/      HUD v eni datoteki (vanilla JS, brez gradnje)
server/tts.py    lokalni TTS pogoni: piper, http (Gepard/Maya1), command, elevenlabs
server/scripts/  mia-start/stop/health/smoke + generatorji certifikatov in boot zvoka
client/          opcijski Windows/Linux odjemalec za pritisk na tipko (z zaznavo budnice)
worker/          opcijska GPU sidecarja: STT strežnik z velikim modelom + statistika za panel Stroji
hermes-plugin/   Hermes vtičnik: agent lahko prikliče/skrije medijske panele na HUD-u
launchd/         predloge za samodejni zagon na macOS (s pripombami o TCC in FD limitih)
docs/            slovenska dokumentacija: SETUP, ARCHITECTURE, TROUBLESHOOTING
docs/en/         ista dokumentacija v angleščini
install.sh       namestitev (brez venv, root ali uporabnik) + manifest
start.sh         zagon, čakanje na strežnik in odpiranje HUD-a v brskalniku
stop.sh          ustavljanje (systemd/launchd/ozadje), status, --restart, --free-ports
uninstall.sh     natančna odstranitev vsega, kar je namestil install.sh
build-package.sh arhiv za namestitev na stroju brez interneta
```

## Varnostni model

- Hermesov API ključ nikoli ne doseže brskalnika: HUD komunicira prek strogo
  omejenega proxyja na glasovnem strežniku.
- Vse HUD končne točke + proxy do plošče + brskalniški WebSocketi so zaščiteni z
  žetonom (piškotek, vnesen enkrat na napravo; `start.sh` ga lahko vnese
  samodejno prek `?token=`).
- Hermesov API in plošča poslušata samo na loopbacku.
- Nizi, ki izgledajo kot skrivnosti, se prekrijejo, preden gredo v oblačni TTS.
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
