# YouTube channels and consent

## Consent dialog

The first visit in a fresh browser profile shows a consent dialog. Before
interacting, click »Sprejmi vse« / »Accept all«:

```js
// browser tool, after the page loads
document.querySelector('button[aria-label*="Accept"], button[aria-label*="Sprejmi"], tp-yt-paper-button[aria-label*="Accept"]')?.click();
```

If the dialog persists, reload once. Do not loop.

## Finding a channel

Do not guess handles. Resolve them:

```bash
yt-dlp "ytsearch5:<channel name>" --get-title --get-id --no-playlist
```

Or use the browser tool:

```
https://www.youtube.com/results?search_query=<channel>&sp=EgIQAg%253D%253D
```

(`sp=EgIQAg%3D%3D` filters to channels.)

## Known patterns

- Channel URL: `https://www.youtube.com/@<handle>`
- Channel videos: `https://www.youtube.com/@<handle>/videos`
- Live: `https://www.youtube.com/@<handle>/streams`
- Playlist: `https://www.youtube.com/playlist?list=<id>`

The user's favourite artists live in `~/.config/mia/favorite-artists.txt`
(managed by `mia-artists`), not in this file. Keep this file for stable
channel-level knowledge only.

## Music on the HUD vs desktop

- HUD: `hud_display(media="video", src=<watch url>, title=<short>)`
- Desktop: `mia-open <watch url>`
- One song at a time: stop the old track on both paths before starting a new
  one (see the **mia-music** skill).

## Showing a channel

If the user says »pokaži kanal X«:

1. Resolve the handle.
2. Open the channel page with `mia-open` (desktop) or `hud_display`
   (HUD iframe).
3. Confirm in one short sentence; do not read the channel description.
