# Podrobna navodila za namestitev

> Angleška različica: [docs/en/SETUP.md](en/SETUP.md)

## 0. Avtomatska namestitev (priporočeno)

`install.sh` opravi razdelke 2–5 tega vodnika v enem prehodu, neposredno v
sistemski Python (brez venv) — tako, kot teče Hermes, nameščen kot root:

```bash
git clone https://github.com/DanijelTech/Mia.git && cd Mia
./install.sh --dry-run               # 1. točno vidi, kaj bo naredil
./install.sh --yes --open            # 2. namesti, zaženi in odpri HUD
./install.sh --with-gepard           #    ...plus Gepard TTS storitev
./install.sh --with-maya1            #    ...ali Maya1 (najboljša izgovorjava)
```

`--open` počaka na glasovni strežnik, izpiše LAN naslov in dostopni žeton ter
odpre `https://<lan-ip>/hud/?token=…` v privzetem brskalniku (HUD ta parameter
pretvori v piškotek in ga odstrani iz naslovne vrstice). Poznejši zagoni in
ustavljanje:

```bash
./start.sh              # zaženi (če je treba), počakaj, odpri HUD
./stop.sh               # ustavi strežnik in TTS storitev (nič ne briše)
./stop.sh --status      # kaj teče in katera vrata so zasedena
./stop.sh --restart     # ustavi + zaženi + odpri
./stop.sh --free-ports  # zadnja možnost: ubij proces, ki drži vrata
```

Namestitvenik:
- namesti pakete (ob „externally managed“ Pythonu sam ponovi z
  `--break-system-packages`),
- prenese slovenski glas,
- ustvari TLS certifikat,
- doda `MIA_HUD_TOKEN` v `~/.hermes/.env`, če ga še ni,
- napiše in zažene systemd enoto (na macOS launchd plist),
- na koncu požene zdravstveno preverjanje.

Vse, kar ustvari, zapiše v manifest
(`/var/lib/mia/install-manifest.json` za root, `~/.local/state/mia/...` za
uporabniško namestitev). `uninstall.sh` se tega manifesta drži, zato je
odstranitev natančna:

```bash
./uninstall.sh --dry-run        # predogled
./uninstall.sh                  # ustavi+onemogoči storitev, odstrani enoto, certifikate,
                                # glasove, boot zvok, loge, server.yaml, vrstico z žetonom
./uninstall.sh --purge-deps     # tudi pip-odstranitev zabeleženih paketov
./uninstall.sh --keep-data      # obdrži glasove/certifikate/loge/config
```

Nikoli se ne dotakne Hermesa, njegovih sej/spomina, tvojih modelov ali izvorne kode.

**Namestitev kot navaden uporabnik** (brez roota) se prilagodi sama: vrat 443 ni
mogoče zagnati brez privilegijev, zato namestitvenik v `server.yaml` zapiše
`tls_ports: [8766]` in HUD živi na `https://<lan-ip>:8766/hud/` (izpiše ga tudi v
povzetku). Ker gre za uporabniško systemd storitev, jo obdržiš aktivno tudi po
odjavi:

```bash
loginctl enable-linger $USER
```

Če pozneje želiš vrata 443, zaženi namestitev kot root (`sudo ./install.sh`).

Za arhiv na stroj brez interneta: `./build-package.sh`.

Testirano na macOS (Apple Silicon) s Hermes Agent v0.16. Predviden čas: ~1 ura.

## 1. Hermes Agent (možgani)

Namesti Hermes Agent in mu nastavi ponudnika LLM — sledi
[uradnemu hitremu začetku](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart).
Preden nadaljuješ, preveri, da `hermes` deluje v terminalu.

Vključi njegov API strežnik v `~/.hermes/.env`:

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=<dolga naključna skrivnost>    # obvezno — poln nabor orodij, tudi terminal!
```

Zaženi gateway (`hermes gateway`) in preveri:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
# {"status": "ok", ...}
```

Priporočeno: v globalni `~/.hermes/SOUL.md` dodaj pravila za govor (kratke
povedi, brez markdowna na glas, nikoli ne izgovori skrivnosti, napovej tvegane
akcije in počakaj na odobritev). Osebnost naj ima agent — ne glasovni strežnik.

### Naj Hermesov gateway teče stalno

Mia se pogovarja s Hermesom prek `127.0.0.1:8642`. Če gateway zaženeš samo v
terminalu (`hermes gateway`), ugasne, ko terminal zapreš — HUD takrat javi
»Hermes API offline«, Mia pa ob govoru reče »Hermesov gateway ni dosegljiv«.
Za trajno delovanje (uporabniška systemd enota):

```ini
# ~/.config/systemd/user/hermes-gateway.service
[Unit]
Description=Hermes Agent gateway (API for Mia)
After=default.target

[Service]
Type=simple
EnvironmentFile=%h/.hermes/.env
ExecStart=%h/.local/bin/hermes gateway
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now hermes-gateway
systemctl --user status hermes-gateway        # active (running)
loginctl enable-linger "$USER"                # preživi odjavo in reboot
```

Če `hermes` ni v `~/.local/bin`, popravi `ExecStart` na pot iz `command -v hermes`.
Hitra alternativa brez systemda: `nohup hermes gateway >> ~/.hermes/gateway.log 2>&1 &`
ali `tmux new -d -s hermes 'hermes gateway'`.

Preveri z:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
```

## 2. Glas: lokalni Piper (offline) ali ElevenLabs (oblak)

Privzeto je **lokalni Piper** — brez ključa, brez omrežja, ~0,7 s za poved na
CPU (4–6× hitreje od realnega časa):

```bash
pip install piper-tts                     # GPL-3.0; teče kot ločen proces
scripts/get-voice.sh sl                   # slovenščina (63 MB) — ali `all` za sl + sr
```

Glasovi pristanejo v `server/voices/` (gitignored). Nato v `config/server.yaml`:

```yaml
tts:
  provider: piper
  piper:
    language: sl                         # sl | sr — izbere iz `voices`
    voices:
      sl: voices/sl_SI-artur-medium.onnx
      sr: voices/sr_RS-serbski_institut-medium.onnx
```

Drugi lokalni pogoni se priklopijo prek `tts.provider: command`: katera koli
binarna datoteka, ki bere besedilo s stdin in piše WAV (ali surov PCM16) na
stdout — npr. ovoj za Gepard ali Maya1. `tts.provider: elevenlabs` ostaja na
voljo za oblak: ustvari ključ na elevenlabs.io, izberi `voice_id`, dodaj
`ELEVENLABS_API_KEY` v `~/.hermes/.env` in ključu podeli pravico
**User → Read**, če želiš vrstico kvote v HUD-u. Flash v2.5 **ne** pokriva
slovenščine ali srbščine — tam uporabi `eleven_v3_conversational`.

### Naravnejši glas: Gepard (opcijsko, GPU z RAM offloadom)

Piper je razločen, a raven. [texdata/Gepard-Slovenian-TTS](https://huggingface.co/texdata/Gepard-Slovenian-TTS)
(Apache-2.0 LoRA, ~555 M, 22 kHz) ima opazno naravnejšo slovensko prozodijo.
Ker je težji, teče kot **storitev** — model se naloži enkrat, ne na vsako poved:

```bash
pip install accelerate
pip install "nemo_toolkit[tts]"
pip install git+https://github.com/nineninesix-ai/gepard-inference

# zagon (napravo izbere samodejno, glej spodaj)
python3 scripts/gepard_tts.py --serve --port 8770 \
    --engine gepard --fallback-piper
```

Nato glasovni strežnik usmeri nanjo:

```yaml
tts:
  provider: http
  http:
    url: http://127.0.0.1:8770/tts
    format: wav
    timeout: 120
    name: gepard
    engine: gepard          # gepard | maya1 — kaj zažene start.sh
```

**GPU proti RAM-u.** Storitev izbere napravo ob zagonu: `--device auto`
(privzeto) uporabi CUDA le, če je takrat prostih vsaj `--min-free-vram-gb` (3 GB),
sicer teče na CPU/RAM. Z `--offload auto` najprej poskusi razcep prek accelerate
`device_map` (del GPU, del RAM), nato pade na čisti CPU, in če nalaganje na CUDA
spodleti, ponovi na CPU, namesto da bi se sesul. Prav to drži Mio pri življenju
na stroju, kjer GPU že zaseda LLM:

| Qwen3-30B-A3B | Whisper large-v3-turbo | Gepard | Gre v 32 GB? |
|---|---|---|---|
| Q4_K_M ~18,6 GB | ~1,6 GB | ~2 GB | da, udobno |
| Q5_K_M ~21,7 GB | ~1,6 GB | ~2 GB | da |
| Q6_K ~26,7 GB | ~1,6 GB | ~2 GB | tesno — TTS pade na CPU |
| Q8_0 ~32,5 GB | — | — | GPU poln — TTS in STT na CPU/RAM |

`--fallback-piper` pomeni: če Gepard ni nameščen ali se ne naloži, storitev še
vedno odgovori s Piperjevim glasom, da Mia ne onemi. Kaj je izbrala, preveri s
`curl -s localhost:8770/health` (`device`, `reason`, `free_vram_gb`).

Ista storitev lahko teče na drugem stroju (npr. GPU delovni postaji) — vpiši
njen naslov v `tts.http.url` in imej `MIA_HUD_TOKEN` na obeh straneh; žeton se
pošilja kot `X-Mia-Token`.

Za trajni zagon uporabi systemd (`systemd --user`, `ExecStart=.../gepard_tts.py
--serve --port 8770`) ali `nohup ... &` na Linuxu, na Windowsu Task Scheduler.

Opomba: LoRA je Apache-2.0; preveri licenco osnovnega modela
(`nineninesix/gepard-1.0`) in NeMo codec-a, preden karkoli distribuiraš.

### Souporaba GPU z LLM (pomembno)

Whisper lahko teče na GPU ali na CPU. **Če LLM teče na isti grafični kartici,
pusti Whisper na CPU** (`stt.device: cpu`, privzeto v primeru konfiguracije):

- na GPU porabi ~1,6 GB za model + ~0,5–0,8 GB za CUDA kontekst ≈ **2,4 GB**;
- nekateri zagonski skripti za LLM (npr. tisti, ki pred nalaganjem preverijo
  proste VRAM) ob tem javijo »GPU že uporablja drug proces« in modela ne naložijo;
- vrstni red je pomemben: če hočeš vseeno GPU STT, najprej zaženi LLM/Hermes,
  šele nato Mio — takrat `device: auto` vidi manj prostega VRAM in izbere CPU,
  če pade pod `min_free_vram_gb`.

Nastavitev zamenjaš z enim ukazom (prepiše `server.yaml` in ponovi zagon):

```bash
./install.sh --stt-device cpu      # ali cuda / auto
systemctl --user restart mia-voice # oz. ./start.sh
nvidia-smi                         # preveri, da Mii ni več na GPU
```

Če hočeš **hitro** GPU prepoznavo in hkrati LLM, daj STT na ločen stroj: panel
»Opcijski dodatki« spodaj opisuje `worker/stt_server.py`, Mia pa uporablja
`stt.remote` in ob nedosegljivosti pade na lokalni CPU model.

### Najboljša izgovorjava: Maya1 (opcijsko, GPU z RAM offloadom)

[Maya1 Slovenian TTS](https://huggingface.co/texdata/Maya1-Slovenian-TTS)
(Apache-2.0) je LoRA na 3B modelu `maya-research/maya1` (Orpheus-style) s
**fonemskim front-endom**: besedilo se pred generiranjem pretvori v espeak-ng
`sl` IPA, kar odpravi težave z naglasom in č/š/ž, ki jih imajo grafemski modeli
(avtor meri najnižjo stopnjo napak na znakih med svojimi različicami: 4,2 %
proti 5,0 % pri grafemski). Je najtežji in najpočasnejši od treh lokalnih glasov.

```bash
./install.sh --with-maya1        # odvisnosti + espeak-ng + systemd enota
# ali ročno:
pip install transformers peft snac soundfile phonemizer accelerate
sudo apt-get install espeak-ng        # macOS: brew install espeak
scripts/gepard_tts.py --serve --port 8770 --engine maya1 --fallback-piper
```

Mio usmeri nanjo enako kot pri Gepardu (`tts.provider: http`, `url:
http://127.0.0.1:8770/tts`).

| | Piper | Gepard | Maya1 |
|---|---|---|---|
| VRAM | 0 (CPU) | ~2 GB | ~6–7 GB (bf16) |
| Hitrost | 4–6× realtime | ~0,5–2 s na poved na GPU | najpočasnejši (3B avtoregresivno) |
| Kakovost | jasno, ravno | naravnejše | najboljša slovenska izgovorjava |
| Dodatki | `piper-tts` | NeMo + `gepard-inference` | `transformers`/`peft`/`snac`/`phonemizer` + espeak-ng |

Nadzor glasu: `--maya-emotion nevtralno|veselo|jezno|gnus|zaspano` zamenja
angleški opis govorca (slovenski adapter je učen na nevtralnem bralnem govoru,
zato je čustveni razpon omejen). `--temperature` je privzeto 0,75 za Maya1
(0,4 za Geparda); `--maya-max-new-tokens` omeji generiranje (~1800 ≈ 10 s).
Vgrajeni `repetition_penalty=1.1` je pomemben: brez njega kratki vnosi včasih ne
izdajo končnega žetona.

Na 32 GB z Qwen3-30B-A3B **Q4** (~18,6 GB) + Whisper (~1,6 GB) se Maya1 usede
(~26 GB skupaj). Pri Q5/Q6 najprej poskusi razcep GPU/RAM prek accelerate, nato
CPU; na CPU poved traja desetine sekund, zato sta tam boljša Piper ali Gepard.

Licence: adapter in osnovni model sta Apache-2.0; SNAC codec
(`hubertsiuzdak/snac_24khz`) ima svojo — preveri pred redistribucijo.
Citiranje: Tadej Fius, MediaAtlas (glej model card).

### Kontrolni seznam za popolnoma brez oblaka

| Element | Nastavitev |
|---|---|
| TTS | `tts.provider: piper` (brez ključa) |
| LLM | lokalni model za Hermesom (`hermes.base_url` → 127.0.0.1) |
| STT | lokalni Whisper (`stt.model: large-v3-turbo`) |
| Oblačni fallback | `hermes.fallback_provider: ""` |
| Zunanji medijski paneli | `hud.allow_external_media: false` |
| Pisave | self-hosted v `server/hud/fonts/` |

Preveri: `curl -s localhost:8765/api/hud-config` vrne `"tts_provider": "piper"`
in `"allow_external_media": false`, `/api/usage` pa `"elevenlabs": null` (brez
odhodnega klica).

### Nadgradnja obstoječe namestitve (jarvis_ai → Mia)

Vse vidno je preimenovano, stare oznake pa še delujejo, da se lahko seliš v
svojem tempu:

| Staro | Novo | Združljivost |
|---|---|---|
| `JARVIS_HUD_TOKEN`, `JARVIS_STT_*`, `JARVIS_SUMMON_URL`, `JARVIS_WORKER_NAME` | `MIA_*` | stare spremenljivke se berejo, če nove ni |
| piškotek `jarvis_token`, glava `X-Jarvis-Token` | `mia_token`, `X-Mia-Token` | oba sprejeta na vhodu |
| `jarvis.local`, `jarvis` | `mia.local`, `mia` | oba dovoljena kot izvor HUD-a |
| `scripts/jarvis-*.sh` | `scripts/mia-*.sh` | stara imena odstranjena — posodobi alias/cron |
| `com.jarvis.voice`, `com.jarvis.dashboard` | `com.mia.voice`, `com.mia.dashboard` | stari LaunchAgenti tečejo, dokler jih ne zamenjaš |
| `hud/jarvis.cer` | `hud/mia.cer` | telefoni morajo namestiti nov profil (stari cert ostane zaupanja vreden) |

Dve spremembi nista kozmetični:

- **`hermes.session_key`** se je preselil iz `jarvis:user:main` v `mia:user:main`.
  To začne novo območje dolgoročnega spomina. Če želiš obdržati stare spomine,
  v `config/server.yaml` nastavi nazaj `session_key: jarvis:user:main`.
- **launchd** je treba na macOS zamenjati:
  ```bash
  launchctl bootout gui/$(id -u)/com.jarvis.voice 2>/dev/null
  launchctl bootout gui/$(id -u)/com.jarvis.dashboard 2>/dev/null
  cp launchd/com.mia.*.plist ~/Library/LaunchAgents/
  scripts/mia-start.sh
  ```

## 3. Strežnik glasovnega cevovoda (ta repo)

```bash
cd server
pip install fastapi uvicorn requests pyyaml numpy \
    RealtimeSTT faster-whisper silero-vad websockets psutil
cp config/server.example.yaml config/server.yaml
```

Opomba: `faster-whisper` in `silero-vad` sta **obvezna** — novejši RealtimeSTT
ju obravnava kot opcijska dodatka in brez njiju odpove ob zagonu (pri VAD tiho,
pri samem pogonu glasno). Prvi zagon traja 60–90 s (uvoz torch + prenos modela),
naslednji so hitrejši.

V `config/server.yaml` nastavi `stt.language` (sl/sr), `tts.provider` in po
potrebi seznam `machines:`. Prvi zagon prenese Whisper model (`large-v3-turbo`
~1,6 GB).

### TLS certifikati (obvezni za mikrofon v brskalniku)

Brskalniki dajo mikrofon samo varnim izvorom:

```bash
scripts/make-certs.sh            # samodejno zazna LAN IP za SAN
```

Brez roota so vrata 443 nedosegljiva; v tem primeru uporabi `tls_ports: [8766]`
in HUD na `https://<lan-ip>:8766/hud/` (namestitvenik to nastavi sam).

Zaupaj `certs/cert.pem` na vsaki napravi (macOS: Keychain; Windows:
`certutil -user -addstore Root cert.pem`; iPhone: prenesi
`https://host:8765/hud/mia.cer`, namesti profil in ga nato omogoči v
Nastavitve → Splošno → O napravi → Nastavitve zaupanja certifikatov).

Opcijsko: preimenuj mDNS ime gostitelja (`sudo scutil --set LocalHostName mia`
na macOS), da HUD živi na `https://mia.local/hud/`. Vrata 443 zahtevajo wildcard
bind, ki je že v primeru konfiguracije.

### Dostopni žeton HUD-a

```bash
echo "MIA_HUD_TOKEN=mia-$(python3 -c 'import secrets;print(secrets.token_hex(3))')" >> ~/.hermes/.env
```

HUD ga vpraša enkrat na napravo. Če spremenljivko izpustiš, je avtentikacija
izklopljena (ni priporočeno).

### Pozdrav ob zagonu (enkratno, lokalno)

```bash
scripts/make-boot-audio.sh TvojeIme    # zapiše hud/audio/boot_*.wav
```

Uporabi isti lokalni Piper glas — brez oblačnih znakov.

### Zagon

```bash
python3 server.py
```

Počakaj ~40 s, da se STT model ogreje, nato odpri `https://TVOJ_HOST/hud/`.
Za pregled vseh petih storitev poženi `scripts/mia-health.sh`.

## 4. Samodejni zagon ob bootu (macOS)

Kopiraj oba plista iz `launchd/`, zamenjaj `/PATH/TO` in `YOUR_USER`, nato:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mia.voice.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mia.dashboard.plist
```

**Preberi komentarje v plistih** — tam sta dve pasti macOS-a (TCC za zunanje
diske in mesto poti do logov), ki ob ignoriranju povzročita tihe zastoje ali
napake `EX_CONFIG`. Vsakodnevno upravljanje: `scripts/mia-{start,stop,restart,health}.sh`.

Na Linuxu `install.sh` napiše systemd enoti `mia-voice` in (opcijsko) `mia-tts`.

## 5. Opcijski dodatki

**Odjemalec za pritisk na tipko** (Windows/Linux stroj z mikrofonom):

```bash
cd client
pip install sounddevice websockets numpy openwakeword
python client.py --push-to-talk --server ws://TVOJ_HOST:8765/ws --list-devices
```

**Statistika GPU delavca** (prikaže se v panelu Stroji): kopiraj
`worker/worker_stats.py` na delavca, `pip install psutil`, zaženi in v vnosu
`machines:` nastavi `stats_url` na `http://worker-ip:8767/stats`.

**GPU prepoznavanje govora** — največji skok v kakovosti, če imaš v LAN-u kateri
koli NVIDIA stroj. Na njem:

```
cd worker
pip install faster-whisper fastapi uvicorn nvidia-cublas-cu12 nvidia-cudnn-cu12
copy run-stt.example.bat run-stt.bat    # vpiši svoj MIA_HUD_TOKEN
run-stt.bat
```

Nato v `server.yaml` odkomentiraj blok `stt.remote:` (usmeri `url` na GPU stroj)
in znova zaženi glasovni strežnik. Rezultat: natančnost `large-v3-turbo` pri
~0,2 s na izjavo, s samodejnim preklopom na lokalni model, kadar je GPU stroj
ugasnjen. Za samodejni zagon ob prijavi v Windows daj `MiaSTT.vbs` v
`shell:startup` (predloga v komentarjih .bat).

**Občutek aplikacije na telefonu**: odpri HUD v Safari/Chrome na telefonu →
Deli → Dodaj na začetni zaslon.

**Da agent postavlja stvari na zaslon** (najbolj impresivno): namesti priloženi
Hermes vtičnik, da »pokaži video o X na zaslonu« materializira holografske
medijske panele na vseh odprtih HUD-ih:

```bash
cp -R hermes-plugin/hud_display ~/.hermes/plugins/hud_display
# uredi ~/.hermes/plugins/hud_display/schemas.py: zamenjaj YOUR_HOST
hermes plugins enable hud_display     # ponovi z -p <profil>, če uporabljaš profile
# znova zaženi hermes gateway
```

Vtičnik potrebuje `MIA_HUD_TOKEN` v `~/.hermes/.env` (isti žeton kot HUD). Ime
mape mora ostati veljavno ime Python modula — vezaji tiho zlomijo odkrivanje
vtičnikov. Agent dobi orodji `hud_display` / `hud_dismiss`; YouTube povezave se
predvajajo kot vgrajen video, `position` left/right omogoča več panelov z
različnih strani.

## 6. Preveri vse skupaj

**Posodobitev na novo izdajo:**

```bash
cd ~/Mia && ./update.sh          # git pull --ff-only + restart storitve
./update.sh --check              # samo prikaže, kaj je novega
```

Tvoj `server/config/server.yaml`, glasovi in certifikati so gitignored in se ob
posodobitvi ne spremenijo; če se je spremenil namestitvenik ali systemd enota,
`update.sh` to pove in predlaga `./install.sh --yes`.

```bash
scripts/mia-health.sh   # vseh pet vrstic OK (in TTS storitev, če je http)
scripts/mia-smoke.sh    # sintetiziran glasovni krog skozi celoten sklad (macOS)
```

Nato pravi test: klikni obroč in vprašaj »kaj je v tvoji spominski datoteki?« —
resnični agent odgovori z resnično vsebino datoteke.
