# Kalibracija glasu po oddaljenosti

> Angleška različica: [docs/en/CALIBRATION.md](en/CALIBRATION.md)

Cilj: Mia prepozna **samo tvoj glas** in to **kjerkoli v hiši** — ob mikrofonu,
na sredini sobe in od daleč. Profil ni več en sam vektor, ampak več
oddaljenostnih odtisov z izmerjeno ravnjo zvoka in lastnim pragom.

## Kako se zažene

Ob prvem obisku HUD-a (ali ko profila še ni) se odpre okno:

```
KALIBRACIJA GLASU PO ODDALJENOSTI
[ZAČNI KALIBRACIJO]  [PREKINI]
```

Mia te vodi skozi tri postaje, vsako ponovi dvakrat:

| Postaja | Oddaljenost | Trajanje | Kaj rečeš |
|---|---|---|---|
| `blizu` | ~0,5 m | 4 s | »Mia, to je moj glas.« |
| `srednje` | 2–3 m | 4 s | »Mia, ali me slišiš?« |
| `dalec` | 5–6 m | 5 s | »Mia, to je moj glas.« |

Po vsakem posnetku Mia pove naslednje navodilo. Če je posnetek prenizek
(< −55 dBFS), ga zavrne in prosi za ponovitev. Na koncu se prikaže:

```
KALIBRACIJA SHRANJENA
blizu: 2 · srednje: 2 · dalec: 2
```

Profil se shrani v `server/voices/speaker_profile.npz` in se **pobere brez
restarta** (mtime se spremlja). V HUD-u **NASTAVITVE → KALIBRIRAJ GLAS** je
kadarkoli ponoviš.

## Terminalna različica

```bash
python3 server/scripts/calibrate_voice.py
python3 server/scripts/calibrate_voice.py --append
python3 server/scripts/calibrate_voice.py --from-files blizu=a.wav srednje=b.wav dalec=c.wav
```

Starejši `enroll_voice.py` še deluje, a ustvari en sam profil; HUD bo zato
predlagal oddaljenostno kalibracijo.

## Kaj je v profilu

`speaker_profile.npz` vsebuje:

- `embedding` — skupni centroid (združljivost s starimi profili),
- `samples` — vsi uporabljeni odtisi,
- `stage_names` — `blizu`, `srednje`, `dalec`,
- `stage_embeddings` — centroid po posamezni oddaljenosti,
- `stage_levels`, `stage_level_stds` — povprečna raven in razpršenost (dBFS),
- `stage_counts` — število posnetkov,
- `stage_thresholds` — prag, izračunan iz samo-podobnosti posnetkov
  (nikoli pod 0,18 in nikoli nad splošnim pragom).

Preverjanje vzame en odtis izjave, ga primerja z **vsemi** centroidi in
uporabi najboljši zadetek. Če je izjava kratka, se prag dvigne za 0,05. V
dnevniku vidiš:

```
SPEAKER match stage=srednje score=0.71 level=-31.4 dBFS
```

## Stroga budnica

V `server/config/server.yaml`:

```yaml
stt:
  continuous:
    wake_words: ["mia", "mijo", "mija", "mio"]
    strict_wake: true
    followup_seconds: 0
    speaker_gate:
      enabled: true
      threshold: 0.30
      require_profile: false
      calibration:
        required: true
```

- `strict_wake: true` pomeni: **vsaka** izjava se mora začeti z »Mia«. Tudi
  takoj po Mijinem odgovoru ne moreš nadaljevati brez budnice.
- `require_profile: true` pomeni: brez kalibriranega profila Mia govora ne
  obdeluje (samo HUD te lahko popelje skozi kalibracijo). Privzeto je `false`,
  da stara namestitev ne ostane nema; v produkciji priporočamo `true`.
- Govor, šum in tuji glasovi se zavržejo **pred** Whisperjem, ko je profil
  kalibriran. To varčuje s CPU in preprečuje, da bi TV ali gostje sprožili
  krog.

Nastavitve lahko spreminjaš tudi v HUD-u **NASTAVITVE** (stroga budnica,
follow-up, prag, zahtevaj profil, zahtevaj kalibracijo). Spremembe se
shranijo v `server/logs/settings.json` in veljajo takoj (tudi za obstoječe
povezave).

## Priporočeni prag

- Začni pri `0.30`.
- Če Mia kdaj ne prepozna tvojega glasu od daleč, znižaj na `0.26–0.28` ali
  ponovi kalibracijo z več posnetki (`--samples 3`).
- Če sprejema tuje glasove, dvigni na `0.34–0.38` in preveri, da je profil
  narejen v isti sobi z enakim mikrofon.
- Vsaka postaja ima svoj prag; oddaljeni posnetki so šumnejši, zato je njihov
  prag lahko nekoliko nižji, a nikoli pod 0,18.

## Diagnostika

```bash
mia-learn status
mia-ctl doctor --json
mia-learn capabilities --refresh
curl -s -H "X-Mia-Token: $MIA_HUD_TOKEN" http://127.0.0.1:8765/api/voice/calibration
```

V HUD-u: **NASTAVITVE** pokaže, ali je profil oddaljenostni, katere postaje
obstajajo in kakšen je prag. **ZMOGLJIVOSTI** vsebuje `voice.speaker_gate` in
`voice.distance_calibration`.

## Pogoste težave

| Simptom | Vzrok | Rešitev |
|---|---|---|
| Mia ne sliši nič | `require_profile: true`, profila ni | klikni KALIBRIRAJ v HUD-u |
| Mia sliši TV | profil manjka / prag prenizek | kalibriraj, dvigni prag |
| Od daleč ne sliši | premalo oddaljenih posnetkov | ponovi kalibracijo, `--samples 3` |
| Od blizu ne sliši | mikrofon se je spremenil | ponovi kalibracijo z istim mikrofonom |
| Kalibracija se ustavi | mikrofon ne pošilja zvoka | dovoljenje brskalnika, HTTPS, `parec` |
