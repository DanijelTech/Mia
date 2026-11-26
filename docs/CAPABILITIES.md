# Seznam zmogljivosti (okljukano / potrjeno / prazno)

Mia ima bogat, strojno preverljiv seznam tega, kar zna na **tem** računalniku.
Ni to seznam želja: vsaka postavka ima ukaz, način preverjanja in status.

## Statusi

| Status | Pomen |
|---|---|
| `confirmed` | uporabnik je potrdil, da deluje |
| `learned` | Mia je to uspešno uporabila (iz revizije) |
| `detected` | orodje/backend je na voljo, a Mia tega še ni uporabila |
| `empty` | še ne preverjeno / prazno polje |
| `failed` | zadnje preverjanje ali uporaba ni uspela |
| `unsupported` | na tem stroju ni backenda; prikazan je namig |

Samo `confirmed` in `learned` se štejeta kot zanesljivi. `empty` in
`unsupported` so priložnost za namestitev ali kalibracijo.

## Kategorije (približno 80 postavk)

- **voice** — mikrofon, STT, TTS, budnica, govorniški odtis, oddaljenostna
  kalibracija, barge-in, HUD mikrofon.
- **audio** — pojačaj/zmanjšaj/nastavi/utišaj/preberi glasnost, izhodne in
  vhodne naprave.
- **display** — seznam zaslonov, svetlost gor/dol/set.
- **desktop** — okna (seznam/fokus/zapri/minimiziraj/maksimiziraj/premakni),
  aplikacije (seznam/zaženi/zapri), vnos (tipkanje/tipke/klik/premik/drsenje),
  posnetek zaslona, odložišče, obvestila, mediji, napajanje
  (zakleni/spanje/restart/ugasni).
- **system** — viri (CPU/RAM/disk/GPU), baterija, uptime, omrežje, zasloni,
  zvočne naprave, procesi (seznam/najdi/ustavi), storitve
  (stanje/zaženi/ustavi/restart).
- **files** — iskanje, nedavne, odpri, pokaži v upravitelju.
- **browser** — odpri URL, Google poišči-in-povej, Google prikaži, HUD panel,
  čiščenje HUD-a.
- **knowledge** — spomin, navade, recepti, napake, drevo veščin, preverjanje,
  Hermes vtičnik.
- **security** — politika nadzora, revizija, prekrivanje skrivnosti.

## Kako se uporablja

### HUD

Panel **ZMOGLJIVOSTI** prikazuje števce in gumb **ODPRI SEZNAM**. Stran
`/hud/capabilities.html` omogoča:

- iskanje po imenu, ukazu in ključnih besedah,
- filtriranje po kategoriji in statusu,
- ✓ **potrdi**, ✗ **ne deluje**, · **počisti**,
- vnos opombe k vsaki postavki (prazno polje, ki se shrani),
- **OSVEŽI DETEKCIJO** (znova zazna orodja).

### CLI

```bash
mia-learn capabilities
mia-learn capabilities --refresh
mia-learn capabilities --category desktop
mia-learn capabilities --status empty
mia-learn capabilities --confirm files.search --notes "testirano 12. 5."
mia-learn capabilities --fail desktop.input.type --notes "Wayland brez wtype"
mia-learn capabilities --json
```

### API

```
GET  /api/capabilities?refresh=1&category=&status=&query=
POST /api/capabilities/refresh
POST /api/capabilities/confirm   {"id":"files.search","status":"confirmed","notes":"..."}
```

## Kako se uči sama

- Ob vsakem `mia-ctl` dejanju se v revizijo zapiše `verified` in
  `verification.status`.
- `mia-learn mine` (in `pending` ter HUD osvežitev) uvozi revizijo in
  pokliče `mark_learned(action, ok)`, ki ustrezno postavko označi kot
  `learned` ali `failed`.
- Uporabnik lahko kadarkoli potrdi ali zavrne postavko v HUD-u; potrjena
  postavka se ne prepiše z avtomatsko detekcijo.

## Preverjanje (verified learning)

Vsak `mia-ctl` rezultat vsebuje:

```json
{
  "verification": {
    "status": "verified",
    "method": "volume_readback",
    "evidence": {"got": 40, "expected": 40}
  }
}
```

- `verified` pomeni, da je post-condition resnično preverjen (npr. okno je
  izginilo, glasnost se ujema, datoteka obstaja, proces je mrtev, storitev je
  aktivna).
- `unknown` pomeni, da varnega post-conditiona ni (tipkanje, klikanje,
  napajanje). Takrat Mia ne trdi, da je bilo preverjeno; počaka na uporabnikov
  ✓ v HUD kartici.
- Samo `verified` epizode (ali uporabnikovo ✓) ustvarijo **recept**. To je
  razlika med “zgleda, da je uspelo” in “dokazano je uspelo”.

## Razširitev seznama

1. Dodaj postavko v `CATALOG` v `server/mia_core/capabilities.py`:
   ```python
   _item("kategorija.nova", "kategorija", "Naslov", "`ukaz`", "ključne besede", "detect")
   ```
2. Če je potrebna posebna detekcija, dodaj vejo v `_detect()`.
3. Za novo `mia-ctl` skupino jo dodaj v `verify_result()` in v `mark_learned()`
   preslikavo.
4. Zaženi `mia-learn capabilities --refresh` in `python -m unittest`.
