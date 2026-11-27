---
name: mia-music
description: "Play, switch and stop music (YouTube), remember what was played, and maintain the user's favourite artists. Use for playlists, albums, moods, 'something I already heard' and any music request beyond the deterministic play/stop path."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [music, youtube, artists, playback, history]
capabilities: [play_music, stop_music, search_youtube, read_history, manage_favourites]
---

# Mia music

## What the voice server already handles

Simple phrases are handled deterministically **before** you see them:

- play: »pusti mi glazbo (v ozadju)«, »poišči X in ga predvajaj«,
  »zaigraj …«, »zamenjaj/spremeni glasbo« (another track)
- stop: »ustavi glasbo / predvajanje / pesem / film«, »ustavi youtube«,
  »zapri vsa okna youtube«, »dovolj glasbe« — stops the HUD panel **and**
  closes the desktop windows
- move to browser: »predvajanje iz ozadja odpri v brskalniku«

You only receive the fancier requests: playlists, albums, moods, history
reasoning, multi-step choices.

## The one-song rule (explicit user requirement)

Before starting a new track, stop the old one on **both** paths:

```bash
mia-close youtube youtu.be soundcloud spotify
# or, through the audited CLI (same effect, reports what it closed):
mia-ctl media close youtube youtu.be soundcloud spotify
```

and

```
hud_dismiss
```

`mia-close` accepts several URL patterns at once and also closes browser
windows whose title matches (for windows opened by `xdg-open` or before the
window registry existed). If `xdotool` is missing it says so and exits 3 —
without it Mia can open windows but never close them.

Never two songs at once. If the user complains about hidden music, call
`hud_dismiss` first — a HUD iframe keeps playing even when nobody looks at it.

## Play flow

1. **Check favourites first**: `mia-artists list`.
2. **Check history**: `tail -n 20 ~/.cache/mia-history.log` (timestamp, URL).
   If the request matches something already played, offer 2–4 saved matches
   aloud and play the chosen id directly — no new search.
3. **Search only if needed**:

   ```bash
   yt-dlp "ytsearch1:<query>" --get-title --get-id --no-playlist
   # first line = title, second line = id
   ```

4. **Stop the old track** (both commands above).
5. **Play**:

   ```bash
   mia-open "https://www.youtube.com/watch?v=<id>"
   ```

   Or, if the user wants it on the HUD:

   ```
   hud_display(media="video", src="https://www.youtube.com/watch?v=<id>", title="<title>")
   ```

6. **Confirm with ONE short phrase** — no commentary about the artist, mood or
   song. The user ordered it; he knows what it is. Examples: »Evo šefe!«,
   »Nazdravlje, šefe!«
7. **Record the track** for taste memory:

   ```bash
   mia-learn record \
     --request "predvajaj <query>" --response "Evo šefe." \
     --source voice --intent music --outcome success \
     --meta '{"entities":[{"kind":"artist","value":"<artist>"},{"kind":"song","value":"<title>"}]}'
   ```

## Stopping

Always do **both**:

```bash
mia-close https://www.youtube.com
```

```
hud_dismiss
```

## Tricky search terms

- »di gona« → likely »da gona« (Serbian/Croatian); try `ytsearch1:digona` or the
  core word.
- Baja Malik / Baja Mali Knindža — both spellings appear; try either.
- If the first result is off-topic (e.g. »goma« returns jewellery), try
  `ytsearch:` or an exact-phrase search before giving up.

## Favourite artists

The user maintains a personal list:

```bash
mia-artists add "X"
mia-artists remove "X"
mia-artists list
```

- Generic »pusti mi glasbo« → offer 2–3 favourites aloud.
- Genre/language request → prefer matching favourites.
- Combine with history: a favourite not heard for a while is a great pick.

## Reference

- `../mia-companion/references/serbian-radio.md` — ExYu radio aggregators.
- `../mia-companion/references/youtube-channels.md` — known channel handles.
