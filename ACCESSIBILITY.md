# Accessibility

Mia should be usable by people with different abilities, devices and network
conditions. This page states what we support, what we know is still hard, and
how to report a barrier.

## Our commitment

- **Keyboard first**: the HUD must be fully operable without a mouse. `Space`
  talks/flushes, `Esc` stops or closes panels, `Enter` sends typed chat, and the
  language switch is a normal button group.
- **Voice and text**: every voice turn has a typed equivalent in the HUD chat.
  The API is plain HTTP/WebSocket and can be driven by an alternative client.
- **Two languages**: the HUD and deterministic replies support Slovenian and
  English (`SLO` / `ENG`); a new string must be added to the translation
  dictionary and its test.
- **No motion requirement**: the brain animation reacts to voice but is not
  required to use Mia. `prefers-reduced-motion` is honoured where practical.
- **Local and private**: no account, cloud key or third-party tracker is needed
  for the offline setup.

## Supported environments

| Area | Supported |
|---|---|
| Browser HUD | Current Chrome/Chromium, Edge, Firefox, Safari; WebSocket + WebAudio + AudioWorklet; microphone requires HTTPS or `localhost` |
| Mobile | Responsive HUD; "Add to Home Screen" for a full-screen app; Bluetooth/USB microphones depend on the OS |
| Desktop control | Linux X11, Wayland (sway/hyprland/wlroots), macOS, Windows; some commands need `xdotool`, `wmctrl`, `playerctl`, `brightnessctl`, `grim`, etc. |
| Speech | Local faster-whisper (CPU/GPU), Piper/Gepard/Maya1 local TTS, optional ElevenLabs; Slovenian/Serbian/English profiles |
| Screen readers | The HUD uses semantic HTML where possible; the canvas brain is decorative and has a text state label. Full screen-reader coverage is still a work in progress. |
| Input | Keyboard, mouse, touch, push-to-talk client; switch/eye-tracker users can use the typed chat and HTTP API |

## Known limitations

- The **brain canvas** is visual only; it is not a control surface for screen
  readers. The same state is shown as text (`LISTENING`, `THINKING`,
  `SPEAKING`, `STOPPED`) and every action has a button.
- **Continuous listening** needs a microphone and browser permission. A
  hardware mute switch or a browser without AudioWorklet falls back to
  push-to-talk.
- **Speaker verification** needs a short enrolment; users with atypical speech
  or a noisy room may need a lower `speaker_gate.threshold` or
  `require_profile: false`.
- **Slovenian/Serbian** speech models are better than English in the default
  offline stack; English works but pronunciation depends on the chosen voice.
- **Colour**: the HUD is a dark cyan/teal theme. High-contrast mode is not a
  separate theme yet; report contrast problems with a screenshot and the exact
  element.
- **Reduced motion**: the scanlines, boot sequence and holographic panels are
  decorative. If they cause discomfort, use the `prefers-reduced-motion` setting
  in your OS/browser and tell us if something still animates.
- **Installer** output is text in a terminal; it is not a GUI installer. The
  commands are documented in [`docs/en/SETUP.md`](docs/en/SETUP.md).

## Reporting an accessibility barrier

Open an **Accessibility** issue using the repository template:

https://github.com/DanijelTech/Mia/issues/new?template=accessibility.yml

Please include:

- what you were trying to do,
- the exact page/button/voice command,
- browser/OS/assistive technology and versions,
- whether keyboard-only, screen reader, zoom, high contrast or reduced motion
  was involved,
- a screenshot or recording if it does not expose private data.

We triage accessibility reports with the `accessibility` label and treat a
blocking barrier as a bug, not a feature request.

## What we are working on

- A high-contrast HUD theme and a larger-text mode.
- A screen-reader pass over the HUD panels, status changes and approval cards.
- Keyboard focus outlines and a skip-to-chat link.
- Captions for the boot greeting and a text transcript of every spoken reply.
- Documenting hardware/OS combinations that are known to work.

If you can help with any of these, see [`CONTRIBUTING.md`](CONTRIBUTING.md) and
open a draft PR early — accessibility work is easiest to review together.
