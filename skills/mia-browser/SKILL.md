---
name: mia-browser
description: "Search the web, open pages on the user's desktop, and display web content on the Mia HUD. Use for facts, news, lookups, Google searches, YouTube channels and any 'show me on screen' request."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [browser, web, search, hud, display]
capabilities: [web_search, open_url, show_on_hud, dismiss_hud, interactive_browsing]
---

# Mia browser and HUD display

## The visibility rule

Browser tools (`browser`, `web_extract`) work in an **invisible** browser. The
user sees nothing. Never say »odprla sem« after a browser-tool call unless you
also opened a visible window or a HUD panel.

Three visible surfaces:

| Surface | How | Use for |
|---|---|---|
| Desktop window | `mia-open "<url>"` | the user wants a real window they can use |
| HUD panel | `hud_display(media=…, src=…, title=…)` | the user wants it on the Mia screen |
| HUD dismiss | `hud_dismiss` | close all holographic panels |

If `hud_display` fails for any reason (import error, 401, timeout), fall back
**once** to `new_tab(url)`. Do not retry `hud_display` in a loop.

## Google: answer vs show (strict distinction)

The user cares about this distinction:

- »Na Googlu poišči in povej mi …« / »Poišči … in mi povej« → **search in the
  background and answer aloud**. Do not open a browser window. The voice server
  turns this into a directive that forces `web_search` + spoken answer.
- »Prikaži mi v Googlu …« / »Pokaži na Googlu …« / »Odpri Google za …« → open
  the Google results page in the user's **visible** browser (`mia-open` /
  `mia-ctl open`). Do not answer from memory instead of showing it.
- Ambiguous »poišči na Googlu …« → answer aloud by default and offer to show
  the page.

## Search and answer

- Quick facts, news, weather, prices: `web_search`, then `web_extract` on the
  best result. Answer aloud in 1–2 sentences. Offer the page on screen.
- »Pokaži mi na Googlu« / »odpri Google za …«:
  `mia-open "https://www.google.com/search?q=<query>"`.
- Interactive browsing (clicking, forms, logins): the `browser` toolset. Show
  the result with `hud_display` if the user should see it.

## HUD panels

```
hud_display(media="video", src="https://www.youtube.com/watch?v=…", title="MUSIC")
hud_display(media="iframe", src="https://example.com", title="NEWS")
hud_display(media="image", src="https://…/image.jpg", title="PHOTO")
hud_dismiss()
```

- `position="left"` / `"right"` for side panels; `"center"` for one large one.
- Keep titles short (≤ 48 characters).
- Do not show secrets, tokens, private messages or banking pages on the HUD.

## YouTube

- Consent dialog: click »Sprejmi vse« with JS before interacting.
- Known handles and patterns: `../mia-companion/references/youtube-channels.md`.
- For playback, prefer the **mia-music** skill (one song at a time, history,
  favourites).

## Desktop windows

- Open: `mia-open "<url>"`.
- Close: `mia-close "<domain or url part>"`; close all Mia windows:
  `mia-close all`.
- If a window »did not open«, retry `mia-open` once, then fall back to
  `xdg-open <url>` (not closable by `mia-close`).
- Never use `google-chrome --new-window` or `pkill` patterns for windows Mia
  opened — they leak or kill the user's own browser.

## Reading vs showing

- The user says »pokaži / na zaslonu / na HUD-u« → HUD panel.
- The user says »odpri« → desktop window.
- The user says »preberi« → use the **mia-productivity** reading protocol; do
  not dump a whole article aloud.
