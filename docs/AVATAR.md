# Mia 3D — premium navzočnost: raziskava in arhitekturna odločitev

> Angleška različica: [en/AVATAR.md](en/AVATAR.md)

Ta dokument je **odločitveni dokument**, ne še implementacija. Cilj: Mio
dvigniti iz "HUD s krogom" v **premium/VIP digitalnega človeka**, ki deluje
živo, govori sinhrono in se odziva na lastno delovanje.

---

## 1. Kaj imamo zdaj (natančen pregled)

Sredina HUD-a je `#reactorWrap` / `<canvas id="reactor">`:

- `STATE_STYLE` določa hitrost vrtenja, barvo, sij in utrip za stanja
  `standby`, `listening`, `thinking`, `tool`, `speaking`, `error`.
- `frame()` vsak frame nariše 4 obroče, 60 tickov in radialno jedro.
- `setState(st, label, hint)` je edini vmesnik za stanje.
- `agent_status` iz strežnika nastavlja `thinking`, `tool_use`, `speaking`,
  `listening`, `stopped`.
- TTS prihaja kot **16 kHz mono int16 PCM** prek WebSocketa; `playChunk()`
  zaključi vsak chunk v `AudioBufferSourceNode` in ga načrtuje na `playhead`
  z ~60 ms prednosti.
- Stavki se v strežniku režejo v `stream_response_audio()` in pošiljajo v
  `_send_tts_sentence()`; **ni časovnih oznak, ni visem, ni fonemov**.
- `mia_say` (opomniki) trenutno uporabi brskalnikov `speechSynthesis`.
- HUD je ena sama HTML datoteka brez build koraka; knjižnice se ne nalagajo
  zunanje (razen če jih dodamo lokalno).

**Zaključek:** manjkajo tri stvari, ki so bistvo "živega" lika:
1. 3D runtime in lik z blendshapi,
2. časovno usklajen govor (visemi/fonemi) iz strežnika,
3. vedenjski režiser (pogled, dihanje, geste, čustva, stanja).

---

## 2. Kaj pomeni "premium/VIP" (merljivi kriteriji)

| Razsežnost | Cilj |
|---|---|
| Prisotnost | oči, koža, lasje, usta, zobje, dihanje; brez vidnega loopa v 2 minutah |
| Sinhronizacija | odmik ustnic od zvoka < 80 ms; slovenski fonemi, ne samo glasnost |
| Odzivnost | prva vidna reakcija < 150 ms po prvem zvoku; brez dodatne zakasnitve zvoka |
| Živost | pogled, utripanje, mikroizrazi, kimanje, geste, dihanje, premikanje teže |
| Čustva | vsaj 8 čustvenih stanj z gladkimi prehodi in mikroizrazi |
| Govorica telesa | geste se ujemajo s pomenom in poudarki, ne naključno |
| Zmogljivost | 60 fps na srednjem GPU, 30 fps na mobilnem; < 2 GB VRAM |
| Zasebnost | privzeto vse lokalno; brez pošiljanja zvoka v oblak |
| Licenca | vsak model, animacija in knjižnica ima dokazljivo komercialno licenco |
| Vzdrževanje | en ukaz za namestitev; jasen fallback na obstoječi obroč |

---

## 3. Možne poti in primerjava

Ocene: 1–5 (5 = najbolje), "trud" je ocena za Mio, ne za splošen projekt.

| Pot | Realizem | Živost | Zakasnitev | Offline | Stroj | Licenca | Trud | Tveganje |
|---|---:|---:|---:|---:|---|---|---|---|
| **A. Browser GLB/VRM + TalkingHead/Three.js** | 4 | 4–5 | 5 | da | integr. GPU | MIT runtime; model posebej | S–M | srednje |
| **B. A + NVIDIA Audio2Face-3D NIM** | 5 | 5 | 4 | da (LAN) | NVIDIA RTX + VRAM | NIM/NGC pogoji | M | srednje |
| **C. Pravi MetaHuman + UE5 + Pixel Streaming** | 5+ | 5 | 3–4 | LAN/GPU strežnik | močan RTX, 24/7 | UE + MetaHuman pogoji | L–XL | visoko |
| **D. Cloud fotorealistični avatar (Azure/D-ID/HeyGen)** | 5 | 5 | 3 | ne | odjemalec | naročnina + pogoji | M | visoko (zasebnost) |
| **E. 2D talking head (MuseTalk/SadTalker)** | 4 (obraz) | 3 | 3 | GPU | NVIDIA | odvisno od modela | M | srednje |
| **F. Vnaprej posneti loopi** | 2 | 1 | 5 | da | nič | odvisno | S | nizko, a ni premium |

### A. Browser GLB/VRM — priporočena prva stopnja

Reference in dejstva:

- **TalkingHead (MIT)** — full-body GLB, Mixamo rig, ARKit + Oculus viseme
  blendshapi, moodi, geste, eye contact, idle, kamera, luči, dinamika las,
  `streamStart/streamAudio/streamStop` za real-time TTS in
  `speakAudio` z visemi/časovnimi oznakami. Podpira tudi lastne blendshape
  animacije. <https://github.com/met4citizen/TalkingHead>
- **three-vrm (MIT)** — VRM 1.0, MToon, spring bones, izrazi, lookAt; več
  kontrole, a več lastnega animacijskega dela. <https://github.com/pixiv/three-vrm>
- **HeadAudio (MIT)** — audio-driven 15 visemov v brskalniku, brez besedila
  in časovnih oznak; odličen fallback, slabša natančnost od fonemskega.
  <https://github.com/met4citizen/HeadAudio>
- **avatar-stage (MIT)** — proceduralne animacije, detekcija rigov, ARKit
  preseti, visemi iz besedila, idle. <https://github.com/rana-jatin/avatar-stage>
- **hermes-avatar (MIT)** — najbližja referenca: Electron + three-vrm,
  12 čustev, fonemski lip-sync, lokalni TTS, 60 fps na RTX 3050 Ti 4 GB.
  <https://github.com/Nurulaev/hermes-avatar>
- **open-annie (Apache-2.0 koda, ločene licence assetov)** — browser 3D lik,
  HeadAudio visemi vsakih 16 ms, pogled/geste/čustva, "gates, not vibes".
  <https://github.com/rehan-remade/open-annie>
- **svelte-vrm-live** — ElevenLabs fonemske časovne oznake → VRM visemi.
  <https://github.com/dexvdev/svelte-vrm-live>

**Prednost:** vse teče v obstoječem brskalniku/HUD-u, brez novega strežnika,
brez clouda. **Slabost:** kakovost je v veliki meri odvisna od modela in
tekstur; "photoreal" v browserju je težji kot v UE5.

### B. NVIDIA Audio2Face-3D NIM

- Pretvori govor v **ARKit blendshape** in čustva; lokalni mikrostoritev
  (NIM/NGC), gRPC/HTTP. <https://github.com/NVIDIA/Audio2Face-3D-Samples>
- Doda vrhunsko obrazno mimiko, mikroizraze in čustva iz zvoka.
- Zahteva NVIDIA GPU in dodatno VRAM; licenca je NIM/NGC, ne MIT.

**Kdaj:** če ima stroj RTX z dovolj VRAM in je lokalni LLM/STT že tam.
**Tveganje:** VRAM konflikt z LLM; dodatna storitev; licenca.

### C. Pravi MetaHuman + Unreal Engine 5 + Pixel Streaming

- Najvišja kakovost: koža, oči, lasje, telo, oblačila, animacije.
- MetaHuman Creator/UE5; Pixel Streaming pošlje WebRTC video v HUD.
  <https://dev.epicgames.com/documentation/en-us/metahuman/metahuman-documentation>
  <https://github.com/EpicGamesExt/PixelStreamingInfrastructure>
- Potrebuje UE5 projekt, GPU strežnik (Windows/Linux), signaling/TURN,
  pakiranje, posodobitve, 24/7 porabo. Licenca: UE EULA + MetaHuman pogoji
  (preveriti komercialno uporabo in distribucijo zunaj UE).

**Kdaj:** ko je na voljo ločen GPU strežnik in je "VIP" vreden operativne
kompleksnosti. **Ne prvi korak.**

### D. Cloud avatarji

Azure Text to Speech Avatar, D-ID, HeyGen in podobno dajo fotorealističen
video brez lokalnega GPU, a pošiljajo zvok/besedilo v oblak, imajo naročnino,
zakasnitev in omejitve. To je v nasprotju z Mia filozofijo "lokalno najprej".
<https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech-avatar/what-is-text-to-speech-avatar>

**Odločitev:** privzeto ne; le kot zavestno opt-in možnost.

### E. 2D talking head

MuseTalk (real-time 30 fps na V100), SadTalker (počasnejši, Apache 2.0) in
Wav2Lip dajo fotorealističen obraz iz slike/videa, a brez pravega telesa in
z drugačnim občutkom. Primerno za "video sporočilo", ne za stalno navzočnost.
<https://github.com/TMElyralab/MuseTalk>
<https://github.com/OpenTalker/SadTalker>

---

## 3.1 Brezplačni kandidati za model — kaj je res "free"

Kratek odgovor: **da, dobesedni MetaHuman je brezplačen za ustvarjanje, a ni
brezplačen samostojen GLB.** Za browser ga je treba bodisi prikazati prek
UE5/Pixel Streaming bodisi izvoziti/pripraviti; za to še vedno veljajo
Epicovi pogoji. Brezplačni "photoreal GLB" za direktni browser je redkost.

| Vir | Kaj dobiš | Licenca / resnica | Za Tier A? |
|---|---|---|---|
| **Epic MetaHuman** <https://www.metahuman.com/> | fotorealističen, polno rigiran lik z lasmi in oblačili; ustvarjanje v brezplačni MetaHuman aplikaciji | brezplačno ustvarjanje; uporaba po MetaHuman/UE pogojih; ni samostojen GLB; za browser najprej UE5 + Pixel Streaming. Novejše izdaje oglašujejo "use in any engine/renderer", a pogoje je treba preveriti. | posredno (Tier C) |
| **MetaHuman kolekcije na Fab** <https://www.fab.com/> | gotovi MetaHuman liki | nekateri brezplačni, mnogi plačljivi; vsak ima svojo licenco | posredno |
| **Ready Player Me** <https://readyplayer.me/> | GLB avatar, Mixamo rig, realističen/stiliziran videz | brezplačen avatar builder/plan; preveri trenutne pogoje za komercialno uporabo in ali model vsebuje ARKit/viseme blendshape | da, po preverjanju |
| **Avaturn** <https://avaturn.me/> | GLB avatar iz selfija; realističen | Basic plan je brezplačen, PRO je plačljiv (na strani je naveden $800/mesec); preveri licenco za komercialno uporabo in export | da, po preverjanju |
| **VRoid Studio + VRM** <https://vroid.com/> | brezplačno orodje, stilizirani anime liki; VRM 1.0 | orodje brezplačno; vsak model ima svojo licenco. pixiv sample modeli: brezplačna uporaba/sprememba/redistribucija po sample terms; Vivi je CC0 | da, a stilizirano |
| **Mixamo** <https://www.mixamo.com/> | brezplačni liki in animacije | Adobe pogoji; brezplačno za vgradnjo v projekt, ne za redistribucijo surovega asseta | za animacije |
| **Blender Studio / Human Base Meshes** | CC0 osnovna geometrija | CC0, a brez končnega riga, blendshapov in tekstur; veliko dela | ne brez dela |
| **Sketchfab CC0** | različni modeli | vsak model svoja licenca; preveri rig, blendshape in komercialno uporabo | morda |

**Praktična izbira:**

- Za **test Tier A** vzemi brezplačen RPM/Avaturn/VRM model in preveri, da ima
  vsaj 15 visemov ali ARKit blendshape. Brez tega lip-sync ne bo premium.
- Za **končni premium** lik kupi/licenciraj model (Character Creator 4,
  Avaturn PRO, VRoid + komercialna licenca) ali pojdi na MetaHuman Tier C.
- "Free" ne pomeni "free to commit": modelov ne dodajaj v git brez
  `ASSET_LICENSE` manifesta; installer naj jih prenese ob soglasju.

---

## 4. Priporočena arhitektura (Tier A zdaj, B in C kot nadgradnja)

```
┌──────────────────────────── HUD (brskalnik) ────────────────────────────┐
│  AvatarView (TalkingHead + Three.js)                                    │
│   ├─ model.glb (Mixamo rig, ARKit 52, Oculus 15, lasje/zobje/jezik)     │
│   ├─ post FX: ACES, bloom, SSAO, DoF, grain, vignette                   │
│   ├─ BehaviourDirector: idle/listening/thinking/tool/speaking/error     │
│   ├─ viseme + emotion + gesture + gaze + blink + breath                 │
│   └─ fallback: obstoječi 2D reactor ring                                │
│                                                                         │
│  WebSocket: avatar_hello, avatar_speech, avatar_state, mia_say          │
│  Audio: 16 kHz PCM (obstoječi kanal) + viseme timeline                  │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
┌────────────────────────── Mia strežnik (Python) ───────────────────────┐
│  avatar/director.py   — značke, čustva, geste, stanja, pravila         │
│  avatar/visemes.py    — slovenščina → Oculus visemi (espeak-ng + pravila)│
│  avatar/timing.py     — trajanje stavka, čakanje, koartikulacija      │
│  avatar/protocol.py   — verzionirani WS dogodki                        │
│  avatar/providers/audio2face.py  (opcijsko, B)                         │
│  avatar/providers/metahuman.py   (opcijsko, C)                         │
│                                                                         │
│  server.py: _send_tts_sentence() dobi avatar_speech pred PCM            │
│           stream_response_audio() pošlje avatar_state                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Protokol (predlog, verzija 1)

Strežnik → HUD:

```json
{"type":"avatar_speech","v":1,"speech_id":42,"seq":0,
 "text":"Dober dan, šefe.","duration_ms":1840,
 "voice":"piper:sl_SI-artur",
 "mood":"warm","gesture":"nod",
 "visemes":["sil","DD","O","PP","E","RR","sil"],
 "times":[0,40,120,300,420,700,1600],
 "durations":[40,80,180,120,280,900,240],
 "energy":[0.0,0.4,0.8,...]}
```

- `visemes` so **Oculus 15**: `sil, PP, FF, TH, DD, kk, CH, SS, nn, RR, aa,
  E, I, O, U`.
- `times`/`durations` v ms, relativno na začetek stavka.
- `energy` je neobvezna krivulja za moč jaw/ustnic (0–1), 60 Hz.
- Sledijo binarni PCM kosi istega stavka. HUD ve, da prvi kos po
  `avatar_speech` pripada temu stavku.
- `avatar_state` (idle/listening/thinking/tool/speaking/paused/error/sleep)
  pošlje strežnik ob prehodih; HUD lahko stanje izpelje tudi iz `agent_status`.
- `avatar_hello` (HUD → strežnik): `{"v":1,"model":"mia","capabilities":
  ["visemes","blendshapes","gestures"]}`.

### 4.2 Sinhronizacija govora za slovenščino

1. **Normalizacija**: odstrani značke, emoji, markdown; številke in
   okrajšave pretvori v izgovorljive besede (TTS jih že zna, visemi ne).
2. **Fonemi**: `espeak-ng -v sl -q -x` (ali `--ipa`) da fonemsko verigo.
   `espeak-ng` je že potreben za Maya1/Gepard; v `install.sh` je predviden.
   Če ga ni, uporabi pravila za slovenščino (je pretežno fonemska pisava:
   č, š, ž, c, h, j, lj, nj, dž).
3. **Preslikava v 15 visemov** (osnutek):
   - `p b m` → PP, `f v` → FF, `t d` → DD, `k g` → kk,
     `tʃ dʒ ʃ ʒ` → CH, `s z ts dz` → SS, `n l ʎ ɲ` → nn,
     `r ər` → RR, `a aː` → aa, `e ɛ` → E, `i ə` → I,
     `o ɔ` → O, `u` → U, `h` → kk/sil, preostalo → sil.
   - Za vsak fonem se določi trajanje in koartikulacijski prehod
     (60–90 ms crossfade).
4. **Trajanje**: vsota nominalnih trajanj se **skalira na dejansko trajanje
   stavka** (`len(pcm)/32000`). Ker je Piper/Gepard stavčni, je to stabilno.
   Za še boljšo natančnost: opcijsko prisilno poravnavo z WhisperX/stable-ts
   (slovenski model) ali Audio2Face (Tier B).
5. **Pošiljanje**: `avatar_speech` + PCM. HUD uporabi
   `streamStart({lipsyncType:"visemes"})` in `streamAudio({audio, visemes,
   vtimes, vdurations})`; ali `speakAudio` na stavek.
6. **Hibridna korekcija**: HeadAudio v brskalniku analizira dejanski zvok in
   20–30 % zmeša s strežniškimi visemi; če timeline manjka, je HeadAudio
   100 % fallback. Tako ni odvisnosti od jezika ali TTS motorja.
7. **Test**: posnemi 50–100 slovenskih stavkov, ročno označi viseme, meri
   odmik in klasifikacijsko točnost. Cilj: < 80 ms, > 85 %.

### 4.3 "Živ" vedenjski režiser

Plasti (aditivno, z maskami):

1. **Dihanje** — 0,2–0,25 Hz, prsni koš/ramena, vedno.
2. **Idle** — utripanje (Poisson 2–6 s, dvojno utripanje), sakade,
   mikro premiki glave, premik teže, občasen pogled vstran.
3. **Pogled** — prioritete: uporabnik/obraz, kazalec, miselni prostor,
   orodje; gladko vodenje; med mišljenjem pogled gor/levo, pred govorom
   nazaj na uporabnika; med poslušanjem 60–80 % očesnega stika in kimanje.
4. **Govor** — visemi + čeljust + obrvi + nagibi glave na poudarkih;
   gesta se začne na poudarjenem zlogu, ne na začetku stavka.
5. **Čustva** — `mood` in mikroizrazi (dvig obrvi, kotiček ustnic) z
   envelopami; najmanj 8 stanj: neutral, warm/happy, sad, angry, fear,
   disgust, love, sleep.
6. **Geste** — `handup, index, ok, thumbup, thumbdown, side, shrug` plus
   lastne (pozdrav, razlaga, ponudba, štetje, "ne vem"); prepreči ponavljanje
   iste geste v 30 s; kolizijska zaščita rok z telesom.
7. **Stanja** — `boot, idle, listening, thinking, tool, speaking, paused,
   error, sleep, celebrate`; prehodi 200–400 ms; barge-in takoj ustavi
   govorno animacijo in preklopi v poslušanje.

Pravila, ki ločijo "premium" od "robota":

- Nobenih naključnih gest, ko Mia ne govori.
- Utripanje na koncu povedi in ob dolgih besedah; ne metronomsko.
- Pogled med mišljenjem odide in se **vrne pred govorom**.
- Kimanje ob koncu uporabnikove izjave (VAD), ne med njo.
- Dihanje se nadaljuje tudi med govorom.
- Mikropavze na vejicah; zaprtje ustnic na b, p, m.
- Amplituda geste sorazmerna čustvu; brez pretiravanja.

### 4.4 Kako se lik poveže z "delovanjem" Mie

- `agent_status` → `avatar_state` (thinking/tool_use/speaking/listening).
- `tool.started` → `tool` stanje + pogled na miselni panel; ob uspehu
  kratek prikim.
- `approval_request` → resen izraz, pogled na kartico.
- `error` → zaskrbljen izraz, rahel odmik.
- `mia_say` (opomniki) → lik izgovori in utripa.
- `verify_request` → vprašujoč izraz.
- Kalibracija → lik gleda v mikrofon, miruje.
- Vsak odgovor LLM lahko vsebuje značke `[mood:...]`, `[gesture:...]`,
  `[look:user]`, `[nod]`, `[pause:300]`; strežnik jih odstrani pred TTS in
  jih prevede v dogodke. Brez značk se čustvo/gesta izpeljeta iz besedila
  in poudarkov (fallback).

### 4.5 Render in "premium" videz

- Three.js WebGL2 (fallback WebGL1), PBR/HDRI studio: topel ključ, hladen
  cyan rim (ujemanje z HUD), mehke sence, kontaktne sence.
- Post FX: ACES tone mapping, bloom, SSAO, DoF na očeh, vignette, film grain,
  rahla kromatska aberacija; vse nadzorovanо z kvalitetnimi profili.
- Koža: subsurface/transmission približek, thickness mapa; oči: iris
  paralaksa, catchlights, tearline; lasje: kartice z anizotropijo in
  dinamiko; zobje/jezik; tkanina.
- Kamera: 3/4 doprsni kader, 50–85 mm ekvivalent, rahel dih kamere,
  paralaksa na kazalec, fokus na oči.
- Obroč iz `#reactor` postane **holografska podlaga** pod likom; ohrani
  barve/utrip stanj, a ni več glavni element. Fallback ostane enak.

### 4.6 Zmogljivost

| Profil | Cilj |
|---|---|
| `ultra` | 60 fps, 1080p, sence + SSAO + DoF, < 2 GB VRAM |
| `high` | 60 fps, brez DoF/SSAO, bloom + sence |
| `balanced` | 30 fps, brez post FX, 720p |
| `fallback` | 2D reactor, brez 3D |

- Model: < 60 MB kompresiran, < 150k trikotnikov, < 120 kosti,
  < 80 blendshapov, KTX2 teksture, Draco/meshopt, LOD.
- Samodejni downgrade, če je frame time > 25 ms 2 s; ob izgubi WebGL
  konteksta fallback in ponovni zagon.
- Nalaganje: prednaloži ob bootu; fallback, če > 8 s.

---

## 5. Licenčna in varnostna pravila

- Vsak model/animacija/tekstura dobi `ASSET_LICENSE` manifest z virom,
  licenco in hashom; brez tega se ne commit-a.
- MIT: Three.js, TalkingHead, HeadAudio, three-vrm, Rhubarb (MIT), avatar-stage.
- Mixamo animacije: Adobe pogoji; preveri komercialno uporabo.
- MetaHuman: UE EULA + MetaHuman pogoji; preveri uporabo zunaj UE in
  distribucijo.
- Audio2Face NIM: NVIDIA NIM/NGC pogoji; preveri produkcijsko licenco.
- Cloud avatarji: samo z izrecnim soglasjem uporabnika; privzeto izklopljeno.
- Zvok ne zapusti stroja brez opt-in.
- Značke iz LLM se prečistijo in omejijo; ne smejo postati ukazi za datoteke.

---

## 6. Fazni načrt in ocene

### Faza 0 — odločitev (ta dokument)
- Izberi tier (A/B/C), slog (fotorealističen/premium stiliziran), GPU,
  licenčni model in ali je potreben popoln offline.
- **Izhod:** podpisana odločitev + seznam assetov.

### Faza 1 — temelj (1–2 tedna)
- Vendor TalkingHead/Three.js; `avatar.js`; model loader; scena, kamera,
  luči, post FX; stanja; idle/listening/thinking/speaking; fallback.
- **Sprejem:** 60 fps, nalaganje < 4 s, fallback, nobenih regresij HUD-a.

### Faza 2 — sinhronizacija govora (1–2 tedna)
- `avatar/visemes.py`, `timing.py`; espeak-ng; Oculus mapping; `avatar_speech`;
  TalkingHead `streamStart/streamAudio`; HeadAudio fallback; testni korpus.
- **Sprejem:** odmik < 80 ms, > 85 % na korpusu, prvi visem < 150 ms.

### Faza 3 — živost (2 tedna)
- Čustva, geste, pogled, dihanje, utripanje, koartikulacija, značke LLM,
  kolizijska zaščita, kamera, prehodi.
- **Sprejem:** 2 min brez vidnega loopa; gesta na poudarku < 120 ms;
  barge-in takoj; brez "mrtvih" oči.

### Faza 4 — VIP nadgradnje (1–3 tedna)
- B: Audio2Face-3D NIM provider (ARKit blendshapes) z A/B primerjavo.
- C: MetaHuman + UE5 + Pixel Streaming; WebRTC player v HUD-u; krmilni
  kanal; ločen GPU strežnik; dokumentacija in fallback.
- **Sprejem:** merljiva kakovost, dokumentirane zahteve, licenca, en ukaz
  za preklop.

---

## 7. Tveganja in omilitve

| Tveganje | Omilitev |
|---|---|
| "Uncanny valley" | začni s premium stiliziranim likom; fotorealizem šele z MetaHuman/Audio2Face; testiraj z uporabnikom |
| Slabša slovenščina | espeak-ng + pravila + korpus; HeadAudio hibrid; ne obljubljaj 100 % |
| VRAM konflikt z LLM | meri; kvalitetni profili; ločen GPU strežnik za C |
| Licenca modela | manifest + pravna preveritev; CC0/MIT ali kupljena licenca |
| Mobilni GPU | `balanced`/fallback; 30 fps; brez post FX |
| Kompleksnost | en runtime (TalkingHead), opcijski providerji; brez drugega UI |

---

## 8. Odločitve, ki jih potrebujemo pred kodo

1. **Tier:** A takoj, B opcijsko, C pozneje? (priporočilo: A → B → C)
2. **Slog:** premium stiliziran (varneje, hitreje) ali fotorealističen
   (MetaHuman/Audio2Face, več strojne opreme in licenc)?
3. **Stroj:** kateri GPU in koliko VRAM? Je na voljo ločen GPU strežnik za
   UE5/Pixel Streaming?
4. **Asset:** kupljen model (Character Creator/Avaturn) ali odprt (VRoid/RPM)?
   Kakšen proračun in licenca?
5. **Zasebnost:** mora biti vse offline? (priporočilo: da)
6. **Jeziki:** slovenščina primarno; ali tudi srbščina/hrvaščina?
7. **Kje:** samo glavni HUD ali tudi mobilni/namizni odjemalec?
8. **Sprejem:** kaj je za vas "premium" — npr. 2 min brez loopa, < 80 ms
   lip-sync, 60 fps?

---

## 9. Priporočilo

**Začni s Tier A:** TalkingHead + licenciran premium ženski GLB + strežniški
viseme director + vedenjski režiser. To je edina pot, ki je hkrati lokalna,
offline, hitra in obvladljiva v tem repozitoriju. Ko bo to stabilno in
izmerjeno, dodaj **B (Audio2Face)** za obrazno mikromimiko in **C (MetaHuman
Pixel Streaming)** kot ločen "VIP" način, če bo strojna oprema upravičila
operativno ceno.

Naslednji korak po potrditvi: implementacija Faze 1 v ločeni veji z
licenciranim testnim modelom, obstoječi 2D obroč pa ostane fallback.

---

## 10. Stanje implementacije (Tier A, dokončana prva različica)

Implementirano:

| Del | Datoteka |
|---|---|
| 3D runtime, kamera, luči, PBR okolje, stanja, pogled, dihanje, utripanje | `server/hud/avatar/avatar.js` |
| Geste in pogled iz oznak (`[gesture:]`, `[look:]`) | `server/hud/avatar/avatar.js`, `server/avatar_visemes.py` |
| Zamenjava modela v teku (`reloadModel`) in izbira pričeske | `server/hud/avatar/avatar.js`, `server/hud/avatar.html` |
| HUD integracija (canvas nad obročem, `avatar-ready`, `avatar_speech`, `mia_say`, opozorilo ob manjkajočem modelu) | `server/hud/index.html` |
| Garderoba in nastavitve | `server/hud/avatar.html`, `/api/avatar/config` |
| Brezplačni ženski model + idle | `server/scripts/fetch-avatar-assets.sh`, `server/hud/avatar/models/` |
| Slovenski visemi in časovna os | `server/avatar_visemes.py` |
| Pošiljanje `avatar_speech` pred PCM | `server/server.py` (`_send_tts_sentence`) |
| Testi | `tests/test_avatar.py` |

**Model:** Ready Player Me kompatibilen ženski GLB iz MIT repozitorija
`readyplayerme/visage` (v2.0.0). Ima 72 ARKit/viseme blendshapov in ločene
kose: lasje, očala, zgornji/spodnji del, obutev. Model se ne commit-a; prenese
se z `server/scripts/fetch-avatar-assets.sh` (ali `install.sh --with-avatar`).

**Kaj uporabnik lahko nastavi:** lasje (pričeska iz seznama tistih, ki jih
model vsebuje, ali brez), barva las, očala, zgornji del, spodnji del, obutev,
barve, odtenek kože, kamera (doprsni/obraz/cel), kakovost, razpoloženje, model
(zamenjava brez osvežitve strani). Nastavitve se shranijo v
`server/logs/avatar.json` in takoj veljajo v glavnem HUD-u.

**Sinhronizacija:** vsak TTS stavek pošlje `avatar_speech` z
`visemes/times/durations` in `duration_ms`; HUD jih veže na dejanski
`playhead`. V istem dogodku potujeta `mood` in `gesture`/`look` iz oznak v
besedilu (npr. `[mood:veselo]`, `[gesture:nod]`, `[look:away]`), zato se
obraz in telo odzivata na vsebino, ne le na glasnost. Če model nima morph
targetov (npr. Avaturn T1), se uporabi samo gibanje glave/telesa; za obrazno
mimiko je potreben T2/ARKit model.

**Geste:** model prinese en Mixamo idle posnetek in nobene knjižnice gest, zato
so geste proceduralne: `nod`, `shake`, `tilt`, `look`, `wave`, `shrug`,
`point`, `bow` so aditivni odmiki glave/prsnega koša z envelope krivuljo.
Nastavijo se z oznako v stavku ali ročno v `/hud/avatar.html` (GESTE IN GOVOR).

**Omejitve:**
- privzeti model ima eno pričesko; seznam prikaže le kose, ki so v modelu,
  dodatne pričeske so nov `.glb` ali dodatni `avaturn_hair_*` kosi,
- geste so proceduralne (nič mocap/animation knjižnice), roke ostanejo v
  idle drži,
- brez Audio2Face in brez MetaHuman Pixel Streaming (fazi B/C iz načrta).

**Avaturn:** T1 demo ima statičen obraz in ni primeren za lip-sync; T2 izvoz
(Animation-ready) podpira ARKit/viseme. Izvoz `.glb` daj v
`server/hud/avatar/models/` in ga izberi v `/hud/avatar.html`; imena
`avaturn_hair_*`, `avaturn_look_0`, `avaturn_shoes_0` so podprta.
