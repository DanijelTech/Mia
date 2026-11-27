# Arhitektura in protokoli

> Angleška različica: [docs/en/ARCHITECTURE.md](en/ARCHITECTURE.md)

## Kako teče glasovni krog

1. Brskalnik zajema mikrofon pri 16 kHz mono (`AudioContext` ustvarjen pri
   16 kHz — to prepreči artefakte pri prevzorčenju, ki pokvarijo natančnost
   Whisperja) in pretaka int16 PCM prek WebSocketa `/ws`.
2. Medtem ko govoriš, strežnik vsakih ~1,2 s požene inkrementalni Whisper in
   pošilja dogodke `partial_transcript` (podnapisi v živo).
3. Ob koncu govora: končni prepis — strežnik najprej poskusi opcijskega **GPU
   STT delavca** (`stt.remote`, velik model, ~0,2 s), sicer pade na lokalni
   Whisper — nato gre prepis do Hermesa prek njegovega **Sessions API**
   (`POST /api/sessions/{id}/chat/stream`, SSE). ID seje se hrani v
   `logs/hermes_sessions.json` po imenu pogovora, zato spomin preživi ponovne
   zagone. Tipkani klepet (`/api/chat`) uporablja *isto* sejo.
4. Razčlenjevanje SSE dogodkov: `run.started` (id kroga → podpora gumbu STOP),
   `assistant.delta` (besedilo), `tool.started` (ime + predogled → aktivnost v
   HUD-u), `assistant.completed` (vključno z zastavico `interrupted`),
   `run.completed` (poraba žetonov), `*approval*` (→ kartice za odobritev).
5. Besedilo se razdeli na povedi, odstrani se markdown/think-bloki, **prekrijejo
   se skrivnosti**, nato vsaka poved steče skozi izbrani TTS pogon
   (`server/tts.py`: privzeto lokalni `piper`, `http` za lokalno storitev, kot je
   Gepard ali Maya1, `command` za lokalni CLI na poved, ali `elevenlabs` za
   oblak) nazaj do odjemalca kot 16 kHz PCM, medtem ko generiranje še teče.
   Lokalni glasovi pri 22,05 kHz se pretakajoče prevzorčijo v procesu.

Zakaj Sessions API in ne `/v1/responses` ali `/v1/runs`: v Hermesu v0.16 so seje
edina površina, ki v enem toku združuje imenovan trajni spomin, ID krogov,
dogodke orodij in dogodke odobritev.

## Učenje, spomin in drevo znanja

Pred vsakim krogom strežnik sestavi omejen `[MIA SPOMIN …]` brief iz lokalne
SQLite baze (`server/mia_core/`): relevantne navade, recepti, anti-vzorci in
dejstva. Brief se doda k pozivu Hermesa; dolžina je omejena s
`learning.context.max_chars` (privzeto 1500). Po krogu se zabeleži epizoda
(zahteva, odgovor, orodja, izid, trajanje, napake, entitete); uspešne epizode
z orodji postanejo recepti, neuspešne pa anti-vzorci.

Kratke fraze »tako je / ni prav / zapomni si postopek« strežnik ujame
deterministično in jih uporabi na zadnji epizodi, preden dosežejo Hermesa.
Vsakih `auto_mine_interval_seconds` (900 s) se izvede izkop navad, uvoz
`control-audit.jsonl` in osvežitev indeksa veščin. Učenje je odporno na
napake: če baza ali drevo nista berljiva, glasovna zanka teče naprej.

Drevo veščin (`skills/`) je eksplicitno: `mia-companion` je koren, otroci
(`mia-desktop`, `mia-learning`, `mia-music`, `mia-browser`,
`mia-productivity`, `mia-diagnostics`) pa lastijo posamezna področja.
`mia-skill validate` preveri imena, starše in `references/`.

## Dva možgana: hiter pogovor + Hermes agent

Vsak krog najprej požene deterministični usmerjevalnik
(`mia_core/autonomy/intents.py`): eksplicitni ukazi se izvedejo brez LLM. Kar
ostane, razdeli `mia_core/brain.py::classify_brain` na **pogovor** in
**dejanje**. Pogovor gre v mali lokalni model (`llm.chat`, OpenAI-kompatibilni
llama-server), dejanja, vprašanja o živih podatkih, URL-ji in poti pa v Hermesa.

Chat model dobi kratek seznam zmogljivosti in strogo navodilo, naj ne našteva
korakov; za dejanja vrne `[[AGENT]]`. Ob prehodu v Hermesa se doda zadnjih nekaj
pogovornih krogov, izid agenta pa se zapiše nazaj v pogovorno zgodovino.

Maya1 ostane skupni glas za oba. Če je chat model izklopljen, nedosegljiv ali
vrne `[[AGENT]]`, krog pade nazaj na Hermesa; če Hermes ne dela, chat model
odgovori, da dejanja ne more izvesti. Konfiguracija je v
`llm.router.enabled`, `llm.chat.*` in `stack.chat.*` (glej
`server/config/server.example.yaml`).

## Samodejnost (mini pod-OS)

`server/mia_core/autonomy/` je stdlib-only plast nad `mia-ctl`:

- `profile.py` zazna stroj (OS, distro, init, paketni upravitelj, namizje,
  orodja, GPU, baterijo, omrežje, privilegije, container), izbere backend za
  vsako zmogljivost, izračuna pripravljenost in pripravi načrt prilagoditve z
  imeni paketov za ta distribucijski sistem. Snapshoti in razlike se shranijo.
- `planner.py` izvaja načrte (koraki `ctl`/`python`/`notify`/`sleep`/`probe`/
  `wait_for`/`plan`) s preflight politike, preverjanjem post-conditionov,
  retryji, rollbackom in dnevnikom v SQLite. Nalogo je mogoče nadaljevati.
- `scheduler.py` hrani vztrajna opravila (`at`, `every`, `daily`) in pravila
  (`condition`, `event`, `idle`). Pogojna pravila so edge-triggered, z
  `for_seconds`, da ne nastane plaz obvestil.
- `health.py` preverja disk, RAM, swap, load, temperaturo, baterijo, omrežje,
  systemd napake, certifikat, učno bazo in zagozdene naloge; vrača oceno,
  opozorila in varno sanacijo.
- `intents.py` je deterministični router slovenskih/angleških sistemskih
  ukazov; ujame samo sidrane vzorce, sicer stavek gre Hermesu.
- `service.py` je skupna fasada; strežnik jo pokliče pred Hermesom
  (`/api/chat` in glasovni krog), `/api/autonomy/*` in HUD jo uporabljata
  neposredno.

Strežnik požene `tick` vsakih `autonomy.interval_seconds` (privzeto 30 s) in
zdravstveni pregled vsakih `health_interval` (300 s). Vse je fail-open: če
profil ali baza odpove, glasovna zanka teče naprej.

## Zagon sklada in diagnoza

`start-mia.sh` zdaj čaka, da storitve res odgovorijo z 2xx (llama-server med
nalaganjem GGUF vrača 503 »Loading model«, kar ni »pripravljeno«), in ob napaki
izpiše zadnje vrstice loga ter namig (VRAM, napačen GPU, manjkajoč GGUF,
zasedena vrata). Koda izhoda 3 pomeni: HUD dela, del sklada pa ne.

## Kalibracija, stroga budnica in preverjanje

- `server/speaker_gate.py` hrani oddaljenostne odtise (bližina/sredina/daleč)
  z ravnjo dBFS in lastnim pragom. Preverjanje vzame en odtis, ga primerja z
  vsemi centroidi in uporabi najboljši zadetek.
- `server/calibration.py` je state machine za vodeno kalibracijo; HUD pošilja
  PCM prek istega WebSocketa. Profil se shrani v
  `server/voices/speaker_profile.npz` in se pobere brez restarta.
- `strict_wake: true` pomeni, da se vsaka izjava mora začeti z »Mia«; v
  strict načinu se follow-up okno ne uporablja.
- Vsaka epizoda ima `verified` in `verification_status`. Samo `verified` ali
  `user_confirmed` epizode ustvarijo recept; nepreverjen uspeh ostane kandidat.
- HUD kartica **JE BILO PRAVILNO?** in `/api/learning/pending` sta povratna
  zanka; `/api/learning/verify` zapiše ✓/✗.
- `server/mia_core/capabilities.py` je seznam ~80 zmogljivosti s statusi
  potrjeno/naučeno/zaznano/prazno/nepodprto; HUD stran
  `/hud/capabilities.html` in `mia-learn capabilities` sta vmesnika.
- `server/hud/settings.html` + `/api/settings` upravljata strogo budnico,
  prag, follow-up, zahtevo po profilu, preverjanje, učenje in dolžino briefa;
  shrani se v `server/logs/settings.json` in velja takoj.

## Nadzor računalnika

`mia-ctl` (v `skills/mia-companion/bin/`) je edini priporočeni vmesnik za
dejanja na stroju. Vsak klic preveri politiko
(`~/.config/mia/control.json`), izvede ukaz kot seznam argumentov (brez
`shell=True`) in zapiše revizijo v
`~/.local/state/mia/control-audit.jsonl`. Revizija se uvozi v učenje, zato
so tudi nadzorna dejanja del navad in receptov.

## WebSocket protokol (glasovni odjemalci)

Odjemalec → strežnik (JSON + binarno):

```
{"type":"start","sample_rate":16000,"format":"pcm_s16le","channels":1,"conversation":"mia-main"?}
<binarni int16 PCM kosi>
{"type":"stop"}
{"type":"stop_run"}
{"type":"approval_decision","run_id":...,"approval_id":...,"decision":"allow"|"deny"}
```

`start` med aktivnim krogom = prekinitev: strežnik prekliče krog, ustavi Hermesov
krog, zabeleži zadnjo izgovorjeno poved in naslednjemu vnosu doda opombo o
prekinitvi, da se agentov spomin ujema s tem, kar si slišal.

Kalibracija uporablja iste binarne kose, a v drugem načinu:

```
{"type":"calibration_start"}          → {"type":"calibration_state", stage, prompt, …}
<binarni PCM kosi>                    → {"type":"calibration_state", …} / calibration_done
{"type":"calibration_cancel"}         → {"type":"calibration_state", active:false}
{"type":"calibration_status"}         → {"type":"calibration_status", status:{…}}
```

Strežnik → odjemalec:

```
status · partial_transcript · transcript · run_started{run_id}
agent_status{state: thinking|tool_use(+tool,preview)|speaking|stopped}
approval_request{data,run_id} · error · done{timing}
<binarni TTS PCM — kosi se režejo na poljubnih bajtnih mejah; shrani neparni bajt>
```

## HTTP končne točke (glasovni strežnik)

| Končna točka | Namen |
|---|---|
| `/hud/` | HUD (statičen, ena datoteka) |
| `/api/hermes/{path}` | **allowlist** proxy do Hermes API, vstavi bearer ključ (GET: health, capabilities, skills, toolsets, jobs, sessions; POST: samo v1/responses) |
| `/api/chat` | tipkani krog klepeta v skupni glasovni seji |
| `/api/voice/calibration` | stanje oddaljenostnega profila + postaje |
| `/api/settings` | branje/pisanje živih nastavitev (budnica, prag, učenje …) |
| `/api/capabilities` | seznam zmogljivosti (potrjeno/naučeno/prazno) |
| `/api/capabilities/refresh`, `/confirm` | detekcija in potrditev |
| `/api/learning/pending` | epizode, ki čakajo na ✓/✗ |
| `/api/learning/verify` | potrditev/zavrnitev epizode |
| `/api/learning/status` | stanje spomina, baze in drevesa veščin |
| `/api/learning/tree` | drevo veščin (flat + nested + health) |
| `/api/learning/brief` | točen brief, ki bi ga model dobil za zahtevo |
| `/api/learning/search` | iskanje po epizodah, receptih, napakah, dejstvih |
| `/api/learning/habits`, `/recipes`, `/mistakes`, `/facts`, `/episodes`, `/events` | pregled spomina |
| `/api/learning/feedback` | ✓/✗ na epizodo (pozitivno/negativno) |
| `/api/learning/remember` | shrani zadnjo epizodo kot recept |
| `/api/learning/recipe`, `/mistake`, `/fact` | ročni vnos |
| `/api/learning/mine`, `/prune`, `/sysinfo`, `/delete`, `/export` | vzdrževanje |
| `/api/autonomy/status`, `/profile`, `/health`, `/jobs`, `/tasks`, `/alerts` | stanje samodejnosti, profil stroja, zdravje, opravila, naloge, opozorila |
| `/api/autonomy/refresh`, `/adapt`, `/remediate`, `/tick`, `/run`, `/text` | zaznava/prilagoditev, sanacija, en cikel urnika, izvedba načrta, naravni ukaz |
| `/api/autonomy/jobs` (POST/DELETE), `/jobs/{id}/toggle`, `/tasks/{id}/resume`, `/cancel` | upravljanje opravil in nalog iz HUD-a |
| `/api/ui/language` | jezik HUD-a (sl/en); vpliva na prevod vmesnika in jezik odgovorov |
| `/api/background`, `/api/background/close`, `/stop`, `/override` | kaj teče v ozadju, ročno zapiranje/ustavljanje in ročni nadzor |
| `/api/machines` | psutil statistika gostitelja + oddaljeni delavci iz konfiguracije |
| `/api/usage` | lokalno štetje žetonov/znakov; kvota ElevenLabs le, kadar je TTS v oblaku |
| `/api/hud-config` | stikala HUD-a: `allow_external_media`, jezik odgovorov, `tts_provider` |
| `/api/summon` | razglasi holografski medijski panel (`{media, src, title, position}` ali `{action:"dismiss"}`) vsem povezanim HUD-om prek WebSocketa — to kliče priloženi Hermes vtičnik `hud_display` |
| vrata 9443 (ločena aplikacija) | TLS povratni proxy Hermesove nadzorne plošče z WebSocket mostom in odstranjevanjem glav, da jo HTTPS HUD lahko vgradi v iframe |

## Model avtentikacije

`MIA_HUD_TOKEN` (okoljska spremenljivka) varuje `/api/*`, proxy do plošče in
WebSockete iz brskalnika (allowlist izvorov + piškotek). Domorodni odjemalci
(PTT odjemalec, testne skripte) ne pošiljajo glave Origin in so izvzeti — model
grožnje je zlonamerno *spletno mesto*, ki dela medizvorne zahteve v tvoj LAN, ne
tvoji lastni procesi. Hermesov API ključ nikoli ne doseže brskalnika.

## Profil zakasnitve (Apple Silicon, lokalni Whisper + Piper)

STT zaključek ~0,7 s · prvi žeton Hermesa 1–3 s (več z orodji) · prvi slišni zvok
~3 s · cel enostaven krog ~4 s. Največji vzvod je LLM za Hermesom; drugi je
velikost Whisper modela.

## Podrobnosti, zakodirane v tem repozitoriju (naučene na težji način)

1. **Pisava SSE**: Hermesov tok dogodkov nima glave charset; Python `requests`
   bi nato dekodiral kot Latin-1 → mojibake. Odjemalec vsili UTF-8.
2. **Vrata 443 na macOS**: neprivilegirani bind deluje le na wildcard naslovu
   (`0.0.0.0`), ne na določenem IP-ju.
3. **launchd + zunanji diski**: glej komentarje v `launchd/*.plist` (TCC zastoj
   na `getcwd`, `EX_CONFIG` pri zunanjih poteh do logov, zagon prek venv
   python-a).
4. **Mikrofon v brskalniku**: zahteva varen kontekst — zato self-signed TLS in
   zaupanje certifikata na vsaki napravi.
5. **Kosi ElevenLabs** prihajajo na poljubnih bajtnih mejah; dekodiraj le
   popolne pare int16 in shrani preostali bajt.
6. **Skoraj tih zvok** povzroči, da faster-whisper vrže izjemo (»No clip
   timestamps found«) — oba STT poti vsako izjemo pri prepisu obravnavata kot
   prazen prepis, ne kot neuspešen krog.
7. **Windows venv + NVIDIA pip kolesa**: cuBLAS/cuDNN DLL-je poišči prek
   `sys.prefix` (`site.getsitepackages()` zgreši venv) in jih dodaj z
   `os.add_dll_directory`, preden uvoziš ctranslate2.
8. **Zagon**: poslušalci se odprejo takoj; lokalni Whisper se ogreva v ozadju,
   natanko enkrat in z zaklepom (startup kavelj se sproži enkrat na uvicorn
   poslušalca — sočasne inicializacije snemalnika sesujejo življenjske dobe).
9. **Omejitve FD**: launchd privzeto dovoli 256 datotečnih opisnikov, strežnik
   pa v mirovanju drži ~244 — nastavi `NumberOfFiles=8192` v plistu (priloženo)
   in zapri pretočne odgovore v `finally` (narejeno), sicer umre v nekaj urah.
10. **Osiroteli STT otroci ukradejo vrata**: podproces snemalnika ima ukazno
    vrstico brez »server.py«, preživi naivne `pkill` in lahko podeduje
    poslušalni socket — naslednji zagon zato prvi bind zgreši in uvicornov
    `SystemExit` prekliče VSE poslušalce. Ustavljaj po lastništvu vrat
    (`lsof -ti tcp:PORT -sTCP:LISTEN | xargs kill -9`) — priloženo v
    `scripts/mia-stop.sh`.
11. **Izbira orodja pri agentu**: proza v SOUL.md ne odvrne modela od privlačnih
    vgrajenih orodij (video je kar naprej »kazal« v svojem nevidnem brskalniku);
    orodje prvega reda z eksplicitno shemo zmaga takoj. Zato
    `hermes-plugin/hud_display`.
