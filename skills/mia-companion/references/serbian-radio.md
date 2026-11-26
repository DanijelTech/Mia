# Serbian / ExYu radio

The user listens to ExYu radio. Individual station sites change often; prefer
aggregators that list many stations with working streams.

## Aggregators

| Site | What it is good for |
|---|---|
| `https://www.exyuradio.rs/` | large ExYu directory, genre and country filters |
| `https://dabplus.live/` | live stations, clean player pages |
| `https://www.radio-now.com/` | fallback directory |

## Flow

1. Ask (or infer) genre: narodna, pop, rock, zabavna, sevdah, kafana.
2. Search the aggregator with the user's words, or open the genre page.
3. Open the station page in a visible window:

   ```bash
   mia-open "https://www.exyuradio.rs/"
   ```

   Or show it on the HUD:

   ```
   hud_display(media="iframe", src="https://www.exyuradio.rs/", title="EXYU RADIO")
   ```

4. If the page exposes a direct stream (`.m3u8`, `.mp3`, `.aac`), you may open
   that URL directly with `mia-open` so the browser plays it.
5. Stop radio like any other media: `mia-close <domain>` and `hud_dismiss`.

## Common stations

Names the user is likely to say: Radio S, Play Radio, Naxi, TDI, Hit FM,
Antena, S Radio, Radio Belgrade (Beograd 202), Radio Novi Sad, BN Radio,
RTRS, Federalna, Kalman, Dukagjini.

Do not hardcode stream URLs — they rotate. Resolve them from the aggregator at
request time.

## Rules

- One audio source at a time: stop music/radio before starting another.
- Do not read station descriptions aloud; confirm in one short sentence.
- If a stream fails, try the next aggregator once, then report honestly.
