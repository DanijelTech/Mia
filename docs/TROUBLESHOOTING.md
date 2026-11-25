# Odpravljanje težav

> Angleška različica: [docs/en/TROUBLESHOOTING.md](en/TROUBLESHOOTING.md)

> Preimenovano iz `jarvis_ai`: strežnik še vedno sprejme staro okoljsko
> spremenljivko `JARVIS_HUD_TOKEN`, piškotek `jarvis_token` in glavo
> `X-Jarvis-Token`, zato nadgradnja ne more tiho izklopiti avtentikacije.

**HUD se naloži, mikrofon pa je blokiran** — si na navadnem http ali na
certifikatu, ki mu brskalnik ne zaupa. Brskalniki zahtevajo varen kontekst za
`getUserMedia`. Zaupaj `certs/cert.pem` na napravi (glej SETUP §3) in uporabi
`https://`.

**Prva povezava po zagonu strežnika poteče** — Whisper se ob zagonu ogreva
(~40 s). `scripts/mia-health.sh`, dokler niso vse vrstice OK.

**»Agent backend offline. Running in basic mode.«** — Hermesov API strežnik ni
dosegljiv **ali** Mia ne vidi ključa. Preveri `API_SERVER_ENABLED`/`API_SERVER_KEY`
v `~/.hermes/.env` tistega uporabnika, ki poganja Mio, in da teče `hermes gateway`:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
```

Če ključa ni v datoteki, ga ustvari in vključi API strežnik:

```bash
grep -q '^API_SERVER_ENABLED=' ~/.hermes/.env || echo 'API_SERVER_ENABLED=true' >> ~/.hermes/.env
grep -q '^API_SERVER_KEY=' ~/.hermes/.env || \
  echo "API_SERVER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" >> ~/.hermes/.env
systemctl --user restart mia-voice        # Mia bere env ob zagonu
hermes gateway                            # gateway mora znova prebrati env
```

Če Hermes teče kot **drug uporabnik** (npr. root), Mia pa kot tvoj, ključ v
`/root/.hermes/.env` ni viden — prekopiraj ga v svojo datoteko ali poganjaj oba
kot isti uporabnik. Če Hermes ni nameščen v `/root`, temveč v tvojem domu, je
datoteka ista (`~/.hermes/.env`) in kopiranje ni potrebno.

**Prepis je napačen / besede so zmešane** — poskrbi, da si na aktualnem HUD-u
(trda osvežitev): mikrofon mora zajemati pri 16 kHz. Pomaga tudi večji model
(`stt.model`). V hrupnih prostorih se približaj mikrofonu; dušenje odmeva je
vklopljeno.

**V odgovorih se pojavlja â€™ / â€œ** — teče star `server.py`; aktualna koda vsili
UTF-8 na Hermesovem SSE toku.

**401 povsod / krog ACCESS CODE** — vneseni žeton se ne ujema z
`MIA_HUD_TOKEN` v `~/.hermes/.env`. Počisti piškotek `mia_token` in poskusi
znova; po spremembi spremenljivke znova zaženi glasovni strežnik.

**LaunchAgent se konča z EX_CONFIG** — poti do logov kažejo na zunanji disk.
`StandardOutPath`/`StandardErrorPath` naj bodo na internem disku.

**LaunchAgent je »running«, a nič ne posluša, log prazen** — TCC blokira proces
z zunanjega diska: obvisi v `getcwd()`/`open()`. Podeli Full Disk Access
`Python.app` v svojem Python frameworku (glej komentarje v plistu) in kliči
**venv** python neposredno — brez ovoja `bash -c 'cd ...'`.

**Vrata 443 »address already in use« ali »permission denied«** — bind na
`0.0.0.0` (macOS oprosti nizka vrata za neprivilegirane le pri wildcard bindu)
in poskrbi, da je prejšnja instanca vrata v celoti sprostila.

**Kvota ElevenLabs kaže »znakov danes« namesto vrstice kvote** — ključu dodeli
pravico User → Read v nadzorni plošči ElevenLabs. (Pri lokalnem TTS je to
pričakovano: kvote ni.)

**Gumb za ustavitev javi »ustavljeno«, Hermes pa je še malo delal** — v Hermesu
v0.16 seje niso registrirane v shrambi krogov (`/stop` vrne 404); ustavitev
deluje tako, da spusti SSE tok. Novejši Hermes to lahko popravi.

**Napaka »No clip timestamps found. Set 'vad_filter'…«** — stara različica;
aktualna koda tih/nerazumljiv zvok obravnava kot prazen prepis na obeh poteh
(lokalni in GPU).

**GPU STT: »Library cublas64_12.dll is not found«** — NVIDIA kolesa niso v
iskalni poti DLL-jev. Uporabi priloženi `worker/stt_server.py` (reši jih prek
`sys.prefix`) in v isti venv namesti `nvidia-cublas-cu12 nvidia-cudnn-cu12`.

**HUD ni dosegljiv ~15 s po ponovnem zagonu** — normalno: omejevanje ponovnih
zagonov pri launchd. Če traja dlje, na gostitelju poženi `scripts/mia-health.sh`.

**HTTPS mrtev, navadna ws vrata pa še odgovarjajo** — dva znana vzroka, oba
popravljena v aktualnih datotekah, a ju je dobro poznati: (1) izčrpani
datotečni opisniki (launchd privzeto 256; priloženi plist dvigne na 8192) in
(2) osirotel STT podproces, ki drži vrata prejšnjega zagona — naslednji zagon
zato zgreši prvi bind in tiho prekliče vse TLS poslušalce. Uporabi
`scripts/mia-stop.sh` — ubija po lastništvu vrat — nikoli goli `pkill`.

**Počasno nalaganje strani iz Windows (10 s+), po IP takojšnje** — Windowsov
mDNS je nezanesljiv z imeni `.local`. Dodaj vrstico v hosts (admin):
`<server-ip> mia.local mia` (najprej daj strežniku DHCP rezervacijo).

**Odgovori agenta so prazni (content null, 0 vhodnih žetonov)** — ponudnik LLM
je brez kvote/dobropisa, ne napaka tukaj. Poglej v dnevnik Hermesovega gatewaya
za 429/402 in v Hermesovem `config.yaml` nastavi `fallback_providers`.

**Agent »kaže« stvari v svojem brskalniku namesto na HUD-u** — namesti in
omogoči priloženi `hermes-plugin/hud_display` (glej SETUP). Prozna navodila ne
premagajo shem orodij; vtičnik jih.

**Telefon ne doseže mia.local** — nekatere različice Androida ne poznajo mDNS;
uporabi surov IP (in ga dodaj v `security.extra_origin_hosts` v `server.yaml`,
da preverjanje izvora WebSocketa sprejme zahtevo).

**`./start-mia.sh` javi, da se je strežnik ustavil med zagonom** — izpiše zadnjih 20
vrstic `server/logs/mia.out`. Najpogosteje manjkajoče odvisnosti
(`pip install …`) ali zasedena vrata. Po odpravi: `./start-mia.sh --no-start`.

**Sistemske storitve se ne zaženejo (container/WSL)** — `install.sh` in
`start-mia.sh` zaznata, da systemd ne teče, in uporabita proces v ozadju
(`server/logs/mia.pid`). V takem okolju systemd enote samo napišeta, ne
aktivirata.

**V HUD-u se pojavi `HTTPConnectionPool(... port=8642): Connection refused` / Mia
reče »Hermesov gateway ni dosegljiv«** — Hermesov gateway ne teče ali pa v
njegovem okolju ni `API_SERVER_ENABLED`/`API_SERVER_KEY`. **Sprememba `.env` ne
velja za že tekoči proces** — po vsakem urejanju je treba `hermes gateway restart`.
Preveri:

```bash
grep -nE '^API_SERVER' ~/.hermes/.env          # ali so vrstice res v datoteki
hermes gateway restart
curl -s -m 2 http://127.0.0.1:8642/health      # {"status":"ok",...}
grep -i "api server" ~/.hermes/logs/gateway.log | tail -3
```

Če tudi po restartu nič ne posluša, zaženi gateway z eksplicitnim okoljem (obide
vsako nalaganje `.env`):

```bash
hermes gateway stop
API_SERVER_ENABLED=true API_SERVER_PORT=8642 \
API_SERVER_KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2) \
hermes gateway
```

V nadaljevanju stari opis: (pogosto zato,
ker je bil zagnan v terminalu, ki si ga zaprl). Zaženi ga trajno:

```bash
hermes gateway install --start-now --start-on-login   # Hermesov upravitelj storitev
hermes gateway status                                 # ali teče (PID)
hermes gateway list                                   # profili
tail -n 40 ~/.hermes/logs/gateway.log                 # išči "API Server"
```

Če v dnevniku piše `API Server: aiohttp not installed`, gateway platformo tiho
preskoči: `python3 -m pip install --user aiohttp` in `hermes gateway restart`.

Če `status --deep` ne omenja `api_server`, gateway v svojem okolju ne vidi
`API_SERVER_ENABLED`/`API_SERVER_KEY` (pri profilih ima vsak svoj `.env`).
Začasno: `nohup hermes gateway >> ~/.hermes/gateway.log 2>&1 &`.

Preveri: `curl -s -H "Authorization: Bearer $(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)" http://127.0.0.1:8642/health`

**HUD javi »glasovni strežnik ni dosegljiv« / »povezava zavrnjena (4401)«** —
brskalnik je spletni priključek (`/ws`) odprl z izvorom, ki ni bil na seznamu.
Pri odpiranju po LAN IP (`https://192.168.1.10:8766/hud/`) je izvor
`https://192.168.1.10:8766`; starejše izdaje so dovolile le `mia.local`,
`localhost` in `127.0.0.1`. Aktualna koda **vedno dovoli isto izvor** (isti
gostitelj kot HUD), tuja spletna mesta pa še vedno zavrne. Po posodobitvi:

```bash
cd ~/Mia && git pull && systemctl --user restart mia-voice
# nato v brskalniku Ctrl+Shift+R
```

Če se pojavi 4401 tudi potem: žeton se ne ujema — odpri
`https://<lan-ip>:8766/hud/?token=$(grep '^MIA_HUD_TOKEN=' ~/.hermes/.env | cut -d= -f2)`.

**V dnevniku gatewaya je `GET /v1/skills failed … TypeError: find_all_skills() got
an unexpected keyword argument 'include_editorial'`** — to ni Mia: njen proxy samo
posreduje klic. Hermes teče iz **izvorne kode** (`…/hermes-agent-src`), uvožena
knjižnica `agent`/`skills` pa je iz nameščenega paketa druge različice. Reši tako,
da oba dela prideta iz istega drevesa:

```bash
cd /mnt/models/hermes-home/hermes-agent-src   # tvoj checkout
git pull
pip install -e .          # ali: hermes update, če tvoja različica to ponuja
hermes gateway restart
```

Dokler to ni urejeno, HUD v panelu VEŠČINE kaže `—` in »ni dosegljivo (Hermes)«.

**HUD kaže »Hermes API offline«, VEŠČINE »?«, AVTOMATIZACIJE »—«, CPU/pomnilnik »—«** —
vse to pride iz Hermesa **prek Miinega proxyja** (`/api/hermes/...`), zato
potrebuje dvoje: (1) `API_SERVER_KEY` v okoljski datoteki uporabnika, ki poganja
Mio, in (2) `hermes gateway` na `127.0.0.1:8642`. Preveri:

```bash
KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health
TOK=$(grep '^MIA_HUD_TOKEN=' ~/.hermes/.env | cut -d= -f2)
curl -s -H "X-Mia-Token: $TOK" http://127.0.0.1:8765/api/hermes/health/detailed | head -c 200
```

Prva vrstica mora vrniti `{"status":"ok",...>`, druga pa JSON prek Miinega
proxyja. Če prva vrne 401/nič: ključ manjka ali gateway ne teče. Panel
DIAGNOSTIKA zdaj zato piše `offline — ključ?` ali `offline — gateway?`.

**Moj LLM se ne zažene: »GPU že uporablja drug proces, pid … /usr/bin/python3«** —
to je **Miin glasovni strežnik**, ki je Whisper naložil na GPU in drži ~2,4 GB.
Če LLM teče na isti kartici, daj Whisper na CPU:

```bash
cd ~/Mia && ./install.sh --stt-device cpu
systemctl --user restart mia-voice
nvidia-smi          # python3 iz Mia ne sme biti več na seznamu
```

Nato zaženi svoj LLM launcher in šele zatem (po potrebi) Mio. Obratno (GPU STT)
je smiselno le, če model naložiš prvi in imaš dovolj VRAM.

**Namestitev uspe, a `mia-health.sh` kaže vse DOWN** — skoraj vedno manjkata
`faster-whisper` in `silero-vad` (RealtimeSTT ju obravnava kot opcijska, ob zagonu
pa brez njiju odpove), ali pa strežnik ne more vezati vrat. Poglej dnevnik:

```bash
journalctl --user-unit mia-voice -n 40 --no-pager   # uporabniška namestitev
sudo journalctl -u mia-voice -n 40 --no-pager       # sistemska
```

Nato poženi `./install.sh --yes` znova — namesti manjkajoče pakete in popravi
`tls_ports`. Trenutna koda posameznega poslušalca ne pusti več, da bi podrl
ostale (prej je neuspešen bind na :443 ubil tudi :8765).

**Storitev se ne zažene: `status=218/CAPABILITIES`** — v enoti je
`AmbientCapabilities=CAP_NET_BIND_SERVICE`, ki ga **uporabniška** systemd enota ne
more dobiti (systemd se zaključi s kodo 218, še preden se Python sploh zažene).
To je bilo v starejših izdajah namestitvenika; v aktualni enoti te vrstice ni več.
Rešitev:

```bash
cd ~/Mia && git pull && ./install.sh --yes     # prepiše enoto brez capabilities
systemctl --user restart mia-voice && ./start-mia.sh
```

**V dnevniku je `PermissionError` ali `SystemExit(1)` pri vratih 443** — tečeš
kot navaden uporabnik. V `server/config/server.yaml` nastavi
`tls_ports: [8766]` in odpri `https://<lan-ip>:8766/hud/`. Namestitvenik to
nastavi sam, če config ustvari on; pri obstoječem configu preveri ročno.

**Mia preneha delovati po odjavi iz sistema** — uporabniške systemd storitve se
ustavijo z zadnjo sejo. Omogoči:

```bash
loginctl enable-linger $USER
```

**`pip --user` je nadgradil skupne pakete (npr. `websockets` 15 → 16)** — to se
zgodi, ker RealtimeSTT zahteva `websockets==16`, uporabniški `site-packages` pa je
deljen z drugo programsko opremo (npr. `gradio-client` zahteva `<16`). Mia dela;
če druga aplikacija zaradi tega odpove, ji namesti svojo različico v ločenem
okolju ali Mio zaženi v venv-u (namestitvenik tega ne počne, ker si želel brez).

**Žeton se je znašel v zgodovini brskalnika** — `?token=` se po prijavi odstrani
iz naslova, a ostane v zgodovini. Če te to moti, uporabi
`./start-mia.sh --no-token-in-url` in žeton vpiši ročno.
