# Mia 3D — premium presence: research and architecture decision

> Slovenian original: [../AVATAR.md](../AVATAR.md)

This is a **decision document**, not yet an implementation. Goal: lift Mia from
"a HUD with a rotating ring" to a **premium/VIP digital human** that feels
alive, speaks in sync and reacts to her own work.

## 1. What exists today (exact audit)

The HUD centre is `#reactorWrap` / `<canvas id="reactor">`:

- `STATE_STYLE` controls ring speed, colour and glow for `standby`,
  `listening`, `thinking`, `tool`, `speaking`, `error`.
- `frame()` draws four rings, 60 ticks and a radial core every frame.
- `setState(st, label, hint)` is the only state interface.
- `agent_status` sets `thinking`, `tool_use`, `speaking`, `listening`,
  `stopped`.
- TTS arrives as **16 kHz mono int16 PCM** over the WebSocket; `playChunk()`
  schedules each chunk on `playhead` with about 60 ms lookahead.
- Sentences are split in `stream_response_audio()` and streamed by
  `_send_tts_sentence()`; **there are no timestamps, visemes or phonemes**.
- `mia_say` (reminders) currently uses the browser `speechSynthesis`.
- The HUD is a single HTML file with no build step and no external libraries
  (unless we vendor them locally).

**Conclusion:** three things are missing:
1. a 3D runtime and a blendshape-capable avatar,
2. time-aligned speech (visemes/phonemes) from the server,
3. a behaviour director (gaze, breathing, gestures, emotion, states).

## 2. What "premium/VIP" means (measurable)

| Dimension | Target |
|---|---|
| Presence | eyes, skin, hair, mouth, teeth, breathing; no visible loop in 2 minutes |
| Sync | audio–lip drift < 80 ms; Slovenian phonemes, not amplitude only |
| Responsiveness | first visible reaction < 150 ms after first audio; no added audio latency |
| Aliveness | gaze, blinks, micro-expressions, nods, gestures, breathing, weight shift |
| Emotion | at least 8 states with smooth transitions and micro-expressions |
| Body language | gestures match meaning and emphasis, never random |
| Performance | 60 fps on a mid GPU, 30 fps mobile; < 2 GB VRAM |
| Privacy | local by default; no audio leaves the machine |
| Licensing | every model, animation and library has a provable commercial licence |
| Operability | one-command install; clear fallback to the current ring |

## 3. Options and comparison

Scores 1–5 (5 = best); effort is for Mia, not for a generic project.

| Option | Realism | Aliveness | Latency | Offline | Hardware | Licence | Effort | Risk |
|---|---:|---:|---:|---:|---|---|---|---|
| **A. Browser GLB/VRM + TalkingHead/Three.js** | 4 | 4–5 | 5 | yes | integrated GPU | MIT runtime; model separate | S–M | medium |
| **B. A + NVIDIA Audio2Face-3D NIM** | 5 | 5 | 4 | yes (LAN) | NVIDIA RTX + VRAM | NIM/NGC terms | M | medium |
| **C. True MetaHuman + UE5 + Pixel Streaming** | 5+ | 5 | 3–4 | LAN/GPU server | strong RTX, 24/7 | UE + MetaHuman terms | L–XL | high |
| **D. Cloud photoreal avatar (Azure/D-ID/HeyGen)** | 5 | 5 | 3 | no | client | subscription + terms | M | high (privacy) |
| **E. 2D talking head (MuseTalk/SadTalker)** | 4 (face) | 3 | 3 | GPU | NVIDIA | model-dependent | M | medium |
| **F. Pre-rendered loops** | 2 | 1 | 5 | yes | none | dependent | S | low, but not premium |

### A. Browser GLB/VRM — recommended first stage

Verified references:

- **TalkingHead (MIT)** — full-body GLB, Mixamo rig, ARKit + Oculus viseme
  blendshapes, moods, gestures, eye contact, idle, camera, lights, dynamic
  bones, `streamStart/streamAudio/streamStop` for real-time TTS and
  `speakAudio` with visemes/timestamps. Supports custom blendshape animation.
  <https://github.com/met4citizen/TalkingHead>
- **three-vrm (MIT)** — VRM 1.0, MToon, spring bones, expressions, lookAt;
  more control, more custom animation work. <https://github.com/pixiv/three-vrm>
- **HeadAudio (MIT)** — audio-driven 15 visemes in the browser, no text or
  timestamps; good fallback, less accurate than phoneme-driven.
  <https://github.com/met4citizen/HeadAudio>
- **avatar-stage (MIT)** — procedural animations, rig detection, ARKit
  presets, visemes from text, idle. <https://github.com/rana-jatin/avatar-stage>
- **hermes-avatar (MIT)** — closest reference: Electron + three-vrm,
  12 emotions, phoneme lip-sync, local TTS, 60 fps on an RTX 3050 Ti 4 GB.
  <https://github.com/Nurulaev/hermes-avatar>
- **open-annie (Apache-2.0 code, separate asset licences)** — browser 3D
  character, HeadAudio visemes every 16 ms, gaze/gesture/emotion gating.
  <https://github.com/rehan-remade/open-annie>
- **svelte-vrm-live** — ElevenLabs phoneme timings → VRM visemes.
  <https://github.com/dexvdev/svelte-vrm-live>

**Pro:** runs in the existing browser/HUD, no new server, no cloud.
**Con:** quality depends heavily on the model and textures; browser photorealism
is harder than UE5.

### B. NVIDIA Audio2Face-3D NIM

- Converts speech into **ARKit blendshapes** plus emotion; local microservice
  (NIM/NGC) with gRPC/HTTP. <https://github.com/NVIDIA/Audio2Face-3D-Samples>
- Adds high-end facial micro-expression and emotion from audio.
- Requires an NVIDIA GPU and extra VRAM; licence is NIM/NGC, not MIT.

**When:** if the machine has an RTX GPU with enough VRAM and already runs the
local LLM/STT. **Risk:** VRAM contention, extra service, licence.

### C. True MetaHuman + Unreal Engine 5 + Pixel Streaming

- Highest fidelity: skin, eyes, hair, body, clothing, animation.
- MetaHuman Creator/UE5; Pixel Streaming sends WebRTC video to the HUD.
  <https://dev.epicgames.com/documentation/en-us/metahuman/metahuman-documentation>
  <https://github.com/EpicGamesExt/PixelStreamingInfrastructure>
- Requires a UE5 project, a GPU server (Windows/Linux), signalling/TURN,
  packaging, updates and 24/7 power. Licence: UE EULA + MetaHuman terms
  (verify commercial use and distribution outside UE).

**When:** a separate GPU server is available and "VIP" justifies the
operational cost. **Not the first step.**

### D. Cloud avatars

Azure Text to Speech Avatar, D-ID, HeyGen and similar provide photoreal video
without a local GPU, but send audio/text to the cloud, require subscriptions,
add latency and impose limits. That conflicts with Mia's local-first design.
<https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech-avatar/what-is-text-to-speech-avatar>

**Decision:** off by default; only an explicit opt-in.

### E. 2D talking heads

MuseTalk (real-time 30 fps on a V100), SadTalker (slower, Apache 2.0) and
Wav2Lip produce a photoreal face from an image/video, but no real body and a
different feel. Suitable for a "video message", not continuous presence.
<https://github.com/TMElyralab/MuseTalk>
<https://github.com/OpenTalker/SadTalker>

## 3.1 Free model candidates — what "free" really means

Short answer: **yes, a literal MetaHuman is free to create, but it is not a
free standalone GLB.** In a browser you either stream it from UE5/Pixel
Streaming or export/prepare it; Epic's terms still apply. A free photoreal GLB
that drops straight into the browser is rare.

| Source | What you get | Licence / truth | For Tier A? |
|---|---|---|---|
| **Epic MetaHuman** <https://www.metahuman.com/> | photoreal, fully rigged character with hair and clothing; created in the free MetaHuman app | free to create; use governed by MetaHuman/UE terms; not a standalone GLB; for the browser the clean path is UE5 + Pixel Streaming. Recent releases advertise "use in any engine/renderer", but verify the terms. | indirectly (Tier C) |
| **MetaHuman collections on Fab** <https://www.fab.com/> | ready-made MetaHumans | some free, many paid; each has its own licence | indirectly |
| **Ready Player Me** <https://readyplayer.me/> | GLB avatar, Mixamo rig, realistic/stylised | free avatar builder/plan; verify current commercial terms and whether the model includes ARKit/viseme blendshapes | yes, after verification |
| **Avaturn** <https://avaturn.me/> | GLB avatar from a selfie; realistic | Basic plan is free, PRO is paid (the site lists $800/month); verify commercial licence and export | yes, after verification |
| **VRoid Studio + VRM** <https://vroid.com/> | free tool, stylised anime characters; VRM 1.0 | tool is free; each model has its own licence. pixiv sample models: free use/modification/redistribution under sample terms; Vivi is CC0 | yes, but stylised |
| **Mixamo** <https://www.mixamo.com/> | free characters and animations | Adobe terms; free to embed in a project, not to redistribute the raw asset | for animations |
| **Blender Studio / Human Base Meshes** | CC0 base geometry | CC0, but no final rig, blendshapes or textures; a lot of work | not without work |
| **Sketchfab CC0** | various models | each model has its own licence; verify rig, blendshapes and commercial use | maybe |

**Practical choice:**

- For a **Tier A test**, take a free RPM/Avaturn/VRM model and verify it has
  at least 15 visemes or ARKit blendshapes. Without that, lip sync will not be
  premium.
- For the **final premium** character, buy/licence a model (Character Creator 4,
  Avaturn PRO, VRoid + commercial licence) or go the MetaHuman Tier C route.
- "Free" does not mean "free to commit": do not add models to git without an
  `ASSET_LICENSE` manifest; the installer should download them with consent.

---

## 3.1 Free model candidates — what "free" really means

Short answer: **yes, a literal MetaHuman is free to create, but it is not a
free standalone GLB.** In a browser you either stream it from UE5/Pixel
Streaming or export/prepare it; Epic's terms still apply. A free photoreal GLB
that drops straight into the browser is rare.

| Source | What you get | Licence / truth | For Tier A? |
|---|---|---|---|
| **Epic MetaHuman** <https://www.metahuman.com/> | photoreal, fully rigged character with hair and clothing; created in the free MetaHuman app | free to create; use governed by MetaHuman/UE terms; not a standalone GLB; for the browser the clean path is UE5 + Pixel Streaming. Recent releases advertise "use in any engine/renderer", but verify the terms. | indirectly (Tier C) |
| **MetaHuman collections on Fab** <https://www.fab.com/> | ready-made MetaHumans | some free, many paid; each has its own licence | indirectly |
| **Ready Player Me** <https://readyplayer.me/> | GLB avatar, Mixamo rig, realistic/stylised | free avatar builder/plan; verify current commercial terms and whether the model includes ARKit/viseme blendshapes | yes, after verification |
| **Avaturn** <https://avaturn.me/> | GLB avatar from a selfie; realistic | Basic plan is free, PRO is paid (the site lists $800/month); verify commercial licence and export | yes, after verification |
| **VRoid Studio + VRM** <https://vroid.com/> | free tool, stylised anime characters; VRM 1.0 | tool is free; each model has its own licence. pixiv sample models: free use/modification/redistribution under sample terms; Vivi is CC0 | yes, but stylised |
| **Mixamo** <https://www.mixamo.com/> | free characters and animations | Adobe terms; free to embed in a project, not to redistribute the raw asset | for animations |
| **Blender Studio / Human Base Meshes** | CC0 base geometry | CC0, but no final rig, blendshapes or textures; a lot of work | not without work |
| **Sketchfab CC0** | various models | each model has its own licence; verify rig, blendshapes and commercial use | maybe |

**Practical choice:**

- For a **Tier A test**, take a free RPM/Avaturn/VRM model and verify it has
  at least 15 visemes or ARKit blendshapes. Without that, lip sync will not be
  premium.
- For the **final premium** character, buy/licence a model (Character Creator 4,
  Avaturn PRO, VRoid + commercial licence) or go the MetaHuman Tier C route.
- "Free" does not mean "free to commit": do not add models to git without an
  `ASSET_LICENSE` manifest; the installer should download them with consent.

## 4. Recommended architecture (Tier A now, B and C later)

```
┌──────────────────────────── HUD (browser) ──────────────────────────────┐
│  AvatarView (TalkingHead + Three.js)                                    │
│   ├─ model.glb (Mixamo rig, ARKit 52, Oculus 15, hair/teeth/tongue)     │
│   ├─ post FX: ACES, bloom, SSAO, DoF, grain, vignette                   │
│   ├─ BehaviourDirector: idle/listening/thinking/tool/speaking/error     │
│   ├─ viseme + emotion + gesture + gaze + blink + breath                 │
│   └─ fallback: current 2D reactor ring                                  │
│                                                                         │
│  WebSocket: avatar_hello, avatar_speech, avatar_state, mia_say          │
│  Audio: 16 kHz PCM (existing channel) + viseme timeline                 │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
┌────────────────────────── Mia server (Python) ──────────────────────────┐
│  avatar/director.py   — tags, emotion, gesture, states, rules           │
│  avatar/visemes.py    — Slovenian → Oculus visemes (espeak-ng + rules)  │
│  avatar/timing.py     — sentence duration, pauses, coarticulation       │
│  avatar/protocol.py   — versioned WS events                             │
│  avatar/providers/audio2face.py  (optional, B)                          │
│  avatar/providers/metahuman.py   (optional, C)                          │
│                                                                         │
│  server.py: _send_tts_sentence() emits avatar_speech before PCM         │
│           stream_response_audio() emits avatar_state                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Protocol (proposal, version 1)

Server → HUD:

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

- `visemes` are the **Oculus 15**: `sil, PP, FF, TH, DD, kk, CH, SS, nn, RR,
  aa, E, I, O, U`.
- `times`/`durations` in ms, relative to the sentence start.
- `energy` is an optional jaw/lip strength curve (0–1) at 60 Hz.
- Binary PCM chunks for the same sentence follow. The HUD knows the first
  chunk after `avatar_speech` belongs to that sentence.
- `avatar_state` (idle/listening/thinking/tool/speaking/paused/error/sleep)
  is sent on transitions; the HUD can also derive it from `agent_status`.
- `avatar_hello` (HUD → server): `{"v":1,"model":"mia","capabilities":
  ["visemes","blendshapes","gestures"]}`.

### 4.2 Speech sync for Slovenian

1. **Normalisation**: remove tags, emoji, markdown; expand numbers and
   abbreviations into pronounceable words (TTS already handles them, visemes
   need the words).
2. **Phonemes**: `espeak-ng -v sl -q -x` (or `--ipa`) gives the phoneme
   string. `espeak-ng` is already required for Maya1/Gepard and is part of
   `install.sh`. If absent, use Slovenian grapheme rules (the orthography is
   largely phonemic: č, š, ž, c, h, j, lj, nj, dž).
3. **Map to the 15 visemes** (draft):
   - `p b m` → PP, `f v` → FF, `t d` → DD, `k g` → kk,
     `tʃ dʒ ʃ ʒ` → CH, `s z ts dz` → SS, `n l ʎ ɲ` → nn,
     `r ər` → RR, `a aː` → aa, `e ɛ` → E, `i ə` → I,
     `o ɔ` → O, `u` → U, `h` → kk/sil, otherwise → sil.
   - Assign a duration and a coarticulation transition (60–90 ms crossfade)
     to each phoneme.
4. **Duration**: scale the sum of nominal durations to the **actual sentence
   duration** (`len(pcm)/32000`). Piper/Gepard are sentence-based, so this is
   stable. For even better accuracy: optional forced alignment with
   WhisperX/stable-ts (Slovenian model) or Audio2Face (Tier B).
5. **Send**: `avatar_speech` + PCM. The HUD uses
   `streamStart({lipsyncType:"visemes"})` and `streamAudio({audio, visemes,
   vtimes, vdurations})`, or per-sentence `speakAudio`.
6. **Hybrid correction**: HeadAudio in the browser analyses the actual audio
   and blends 20–30 % with the server visemes; if the timeline is missing,
   HeadAudio is the 100 % fallback. No dependency on language or TTS engine.
7. **Test**: record 50–100 Slovenian sentences, annotate visemes, measure
   drift and classification accuracy. Target: < 80 ms, > 85 %.

### 4.3 "Alive" behaviour director

Layers (additive, with masks):

1. **Breathing** — 0.2–0.25 Hz, chest/shoulders, always on.
2. **Idle** — blinking (Poisson 2–6 s, double blinks), saccades, micro head
   motion, weight shift, occasional glance.
3. **Gaze** — priorities: user/face, cursor, thought space, tool panel;
   smooth damping; look up/left while thinking, back to the user before
   speaking; 60–80 % eye contact while listening, with nods.
4. **Speech** — visemes + jaw + brows + head beats on stress; a gesture
   starts on the stressed syllable, not at the sentence start.
5. **Emotion** — `mood` and micro-expressions (eyebrow flash, lip corner)
   with envelopes; at least 8 states: neutral, warm/happy, sad, angry, fear,
   disgust, love, sleep.
6. **Gesture** — `handup, index, ok, thumbup, thumbdown, side, shrug` plus
   custom (wave, explain, offer, count, "I don't know"); no repeated gesture
   within 30 s; hand/body collision guard.
7. **States** — `boot, idle, listening, thinking, tool, speaking, paused,
   error, sleep, celebrate`; 200–400 ms transitions; barge-in stops speech
   animation immediately and switches to listening.

Rules that separate premium from robotic:

- No random gestures when Mia is not speaking.
- Blink at sentence end and on long words; never metronomic.
- Look away while thinking and **return before speaking**.
- Nod when the user finishes (VAD), not in the middle.
- Breathing continues while speaking.
- Micro-pauses at commas; lip closure on b, p, m.
- Gesture amplitude proportional to emotion; no over-acting.

### 4.4 How the avatar connects to Mia's work

- `agent_status` → `avatar_state` (thinking/tool_use/speaking/listening).
- `tool.started` → `tool` state + glance at the thought panel; a short nod on
  success.
- `approval_request` → serious expression, glance at the card.
- `error` → concerned expression, slight recoil.
- `mia_say` (reminders) → the avatar speaks and blinks.
- `verify_request` → questioning expression.
- Calibration → the avatar looks at the microphone and holds still.
- Any LLM answer may contain `[mood:...]`, `[gesture:...]`, `[look:user]`,
  `[nod]`, `[pause:300]`; the server strips them before TTS and maps them to
  events. Without tags, emotion/gesture are inferred from text and emphasis
  as a fallback.

### 4.5 Rendering and the premium look

- Three.js WebGL2 (WebGL1 fallback), PBR/HDRI studio: warm key, cool cyan rim
  (matches the HUD), soft shadows, contact shadows.
- Post FX: ACES tone mapping, bloom, SSAO, eye DoF, vignette, film grain,
  slight chromatic aberration; all controlled by quality profiles.
- Skin: subsurface/transmission approximation, thickness map; eyes: iris
  parallax, catchlights, tearline; hair: anisotropic cards with dynamics;
  teeth/tongue; cloth.
- Camera: 3/4 bust framing, 50–85 mm equivalent, subtle camera breathing,
  pointer parallax, focus on the eyes.
- The `#reactor` ring becomes a **holographic pedestal** under the avatar;
  it keeps the state colours/pulse but is no longer the main element. The
  current ring remains the fallback.

### 4.6 Performance

| Profile | Target |
|---|---|
| `ultra` | 60 fps, 1080p, shadows + SSAO + DoF, < 2 GB VRAM |
| `high` | 60 fps, no DoF/SSAO, bloom + shadows |
| `balanced` | 30 fps, no post FX, 720p |
| `fallback` | 2D reactor, no 3D |

- Model: < 60 MB compressed, < 150k triangles, < 120 bones, < 80 blendshapes,
  KTX2 textures, Draco/meshopt, LOD.
- Automatic downgrade if frame time > 25 ms for 2 s; on WebGL context loss,
  fall back and retry.
- Loading: preload on boot; fallback if > 8 s.

## 5. Licence and security rules

- Every model/animation/texture gets an `ASSET_LICENSE` manifest with source,
  licence and hash; no manifest, no commit.
- MIT: Three.js, TalkingHead, HeadAudio, three-vrm, Rhubarb (MIT), avatar-stage.
- Mixamo animations: Adobe terms; verify commercial use.
- MetaHuman: UE EULA + MetaHuman terms; verify use outside UE and distribution.
- Audio2Face NIM: NVIDIA NIM/NGC terms; verify production licence.
- Cloud avatars: only with explicit user consent; off by default.
- Audio never leaves the machine without opt-in.
- LLM tags are sanitised and bounded; they never become file commands.

## 6. Phased plan and estimates

### Phase 0 — decision (this document)
- Choose tier (A/B/C), style (photoreal/premium stylised), GPU, licensed
  model, and whether full offline is required.
- **Output:** signed decision + asset list.

### Phase 1 — foundation (1–2 weeks)
- Vendor TalkingHead/Three.js; `avatar.js`; model loader; scene, camera,
  lights, post FX; states; idle/listening/thinking/speaking; fallback.
- **Accept:** 60 fps, load < 4 s, fallback works, no HUD regressions.

### Phase 2 — speech sync (1–2 weeks)
- `avatar/visemes.py`, `timing.py`; espeak-ng; Oculus mapping;
  `avatar_speech`; TalkingHead `streamStart/streamAudio`; HeadAudio fallback;
  test corpus.
- **Accept:** drift < 80 ms, > 85 % on the corpus, first viseme < 150 ms.

### Phase 3 — aliveness (2 weeks)
- Emotion, gesture, gaze, breathing, blinking, coarticulation, LLM tags,
  collision guard, camera, transitions.
- **Accept:** 2 minutes without a visible loop; gesture on stress < 120 ms;
  instant barge-in; no "dead eyes".

### Phase 4 — VIP upgrades (1–3 weeks)
- B: Audio2Face-3D NIM provider (ARKit blendshapes) with A/B comparison.
- C: MetaHuman + UE5 + Pixel Streaming; WebRTC player in the HUD; control
  channel; separate GPU server; docs and fallback.
- **Accept:** measurable quality, documented requirements, licence, one-command
  switch.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Uncanny valley | start with a premium stylised character; photorealism only with MetaHuman/Audio2Face; test with the user |
| Weak Slovenian | espeak-ng + rules + corpus; HeadAudio hybrid; do not promise 100 % |
| VRAM conflict with the LLM | measure; quality profiles; separate GPU server for C |
| Model licence | manifest + legal review; CC0/MIT or purchased licence |
| Mobile GPU | `balanced`/fallback; 30 fps; no post FX |
| Complexity | one runtime (TalkingHead), optional providers; no second UI |

## 8. Decisions needed before code

1. **Tier:** A now, B optional, C later? (recommendation: A → B → C)
2. **Style:** premium stylised (safer, faster) or photoreal (MetaHuman/
   Audio2Face, more hardware and licences)?
3. **Hardware:** which GPU and how much VRAM? Is a separate GPU server for
   UE5/Pixel Streaming available?
4. **Asset:** purchased model (Character Creator/Avaturn) or open (VRoid/RPM)?
   What budget and licence?
5. **Privacy:** must everything be offline? (recommendation: yes)
6. **Languages:** Slovenian primary; also Serbian/Croatian?
7. **Where:** main HUD only, or also mobile/desktop client?
8. **Acceptance:** what is "premium" for you — e.g. 2 minutes without a loop,
   < 80 ms lip-sync, 60 fps?

## 9. Recommendation

**Start with Tier A:** TalkingHead + a licensed premium female GLB + a
server-side viseme director + a behaviour director. It is the only path that
is local, offline, fast and manageable inside this repository. Once stable and
measured, add **B (Audio2Face)** for facial micro-expression and **C (MetaHuman
Pixel Streaming)** as a separate "VIP" mode if the hardware justifies the
operational cost.

Next step after approval: implement Phase 1 in a separate branch with a
licensed test model, keeping the current 2D ring as the fallback.

---

## 10. Implementation status (Tier A, first release)

Implemented:

| Part | File |
|---|---|
| 3D runtime, camera, lights, PBR environment, states, gaze, breathing, blinking | `server/hud/avatar/avatar.js` |
| HUD integration (canvas over the ring, `avatar-ready`, `avatar_speech`, `mia_say`) | `server/hud/index.html` |
| Wardrobe and settings | `server/hud/avatar.html`, `/api/avatar/config` |
| Free female model + idle | `server/scripts/fetch-avatar-assets.sh`, `server/hud/avatar/models/` |
| Slovenian visemes and timeline | `server/avatar_visemes.py` |
| `avatar_speech` before PCM | `server/server.py` (`_send_tts_sentence`) |
| Tests | `tests/test_avatar.py` |

**Model:** a Ready Player Me-compatible female GLB from the MIT
`readyplayerme/visage` repository (v2.0.0). It has 72 ARKit/viseme blendshapes
and separate hair, glasses, top, bottom and footwear meshes. The model is not
committed; fetch it with `server/scripts/fetch-avatar-assets.sh` (or
`install.sh --with-avatar`).

**User controls (71 settings):** wardrobe (8 presets, per-piece colour and
fabric material, glasses), hair (styles present in the model or off, 6 shape
variants, colour, length, volume), skin and eye palettes, shape (6 body types
and 12 sliders: height, build, head, eyes, neck, shoulders, hips, hands, feet),
face (mood, smile, brow raise, wide eyes), behaviour (blink, breathing, sway,
pointer gaze, idle, gesture strength), camera (7 shots plus distance, height,
yaw, FOV, parallax, orbit), lights (8 presets, per-light colour and intensity,
exposure, environment), background and render (quality, shadows, FPS, pixel
ratio), model and idle clip. Everything is saved to `server/logs/avatar.json`,
applies to the main HUD immediately, and can be exported/imported as JSON,
randomised or reset. The schema lives in `server/hud/avatar/presets.js`;
`server/avatar_config.py` mirrors and validates it, and a test enforces the
parity.

**Sync:** each TTS sentence sends `avatar_speech` with
`visemes/times/durations` and `duration_ms`; the HUD anchors them to the
actual `playhead`. The same event carries `mood` and `gesture`/`look` from
inline tags (`[mood:happy]`, `[gesture:nod]`, `[look:away]`), so the face and
body react to content, not just loudness. A model without morph targets (e.g.
Avaturn T1) only gets head/body motion; facial animation needs a T2/ARKit
model.

**Gestures:** the free model ships one Mixamo idle clip and no gesture
library, so gestures are procedural: `nod`, `shake`, `tilt`, `look`, `wave`,
`shrug`, `point`, `bow` are additive head/chest offsets with an envelope.
Trigger them with a tag in the sentence or by hand on `/hud/avatar.html`
(GESTE IN GOVOR).

**Limits:**
- the default model has one hairstyle; the list only shows meshes the model
  has, extra hairstyles are another `.glb` or extra `avaturn_hair_*` meshes,
- gestures are procedural (no mocap/animation library), arms stay in the idle
  pose,
- no Audio2Face and no MetaHuman Pixel Streaming (phases B/C of the plan).

**Screenshots:** [HUD with the 3D character](../screenshots/01-hud.webp) ·
[LIK page, full body](../screenshots/02-lik-cel-lik.webp) ·
[face close-up](../screenshots/03-obraz.webp)

**Avaturn:** the T1 demo has a static face and is unsuitable for lip sync; a
T2 (Animation-ready) export supports ARKit/visemes. Drop the `.glb` into
`server/hud/avatar/models/` and select it in `/hud/avatar.html`; the
`avaturn_hair_*`, `avaturn_look_0` and `avaturn_shoes_0` names are supported.
