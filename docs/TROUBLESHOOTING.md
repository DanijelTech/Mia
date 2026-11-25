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
dosegljiv. Preveri `API_SERVER_ENABLED/KEY` v `~/.hermes/.env` in da teče
`hermes gateway`; preveri s `curl -H "Authorization: Bearer $KEY"
http://127.0.0.1:8642/health`.

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

**`./start.sh` javi, da se je strežnik ustavil med zagonom** — izpiše zadnjih 20
vrstic `server/logs/mia.out`. Najpogosteje manjkajoče odvisnosti
(`pip install …`) ali zasedena vrata. Po odpravi: `./start.sh --no-start`.

**Sistemske storitve se ne zaženejo (container/WSL)** — `install.sh` in
`start.sh` zaznata, da systemd ne teče, in uporabita proces v ozadju
(`server/logs/mia.pid`). V takem okolju systemd enote samo napišeta, ne
aktivirata.

**Žeton se je znašel v zgodovini brskalnika** — `?token=` se po prijavi odstrani
iz naslova, a ostane v zgodovini. Če te to moti, uporabi
`./start.sh --no-token-in-url` in žeton vpiši ročno.
