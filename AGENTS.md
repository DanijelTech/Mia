# AGENTS.md — working notes for Mia

## What this repository is

Mia is a local-first Slovenian voice assistant and Iron-Man-style HUD built on
Hermes Agent. It runs on the user's own machine: Whisper (STT), Piper/Gepard/
Maya1 (TTS), a local LLM behind Hermes, and a browser HUD.

The current major addition is the **learning/knowledge core** and the
**audited computer-control CLI**:

- `server/mia_core/` — stdlib-only Python package: SQLite memory, episodes,
  habits, recipes, anti-patterns, skill tree, capability checklist, context
  brief, `mia-learn` CLI.
- `server/speaker_gate.py` — distance-aware ECAPA profiles (near/mid/far);
  `server/calibration.py` — guided HUD calibration state machine.
- `server/hud/settings.html` — live settings; `server/hud/capabilities.html` —
  confirmed/learned/empty checklist.
- `skills/` — granular skill tree (`mia-companion` root + 6 children), each
  with `SKILL.md` front matter and `references/`.
- `skills/mia-companion/bin/mia-ctl` — cross-platform, policy-checked, audited
  control of windows/apps/input/screenshots/clipboard/media/power/files.
- `server/hud/learning.html` — HUD page for memory, tree, habits, recipes,
  mistakes, episode log and search.
- `hermes-plugin/mia_learning/` — first-class Hermes tools
  (`memory_brief/search/feedback/remember/fact/mistake/status`, `skill_tree`)
  that call `/api/learning/*`; `hermes-plugin/hud_display/` remains the media
  panel plugin; `hermes-plugin/mia_autonomy/` exposes
  `system_status/profile/health/adapt/plans/run_plan/command/jobs/tasks/alerts`
  over `/api/autonomy/*`.
- 3D avatar: `server/hud/avatar/avatar.js` (Three.js runtime, wardrobe, gaze,
  breathing, blink, ARKit/viseme blending, live model swap), `presets.js`
  (79 settings, schema, presets), `characters.js` (9 female appearance
  bundles), `motion.js` (26 procedural full-body actions), `hair.js` (10
  procedural wigs), `garments.js` (accessories, dresses, robot rig),
  `server/hud/avatar.html` (settings deck), `server/avatar_visemes.py`
  (Slovenian → Oculus 15 timeline), and `_send_tts_sentence()` emits
  `avatar_speech` before each sentence's PCM. Models are downloaded by
  `server/scripts/fetch-avatar-assets.sh` and are gitignored; the HUD keeps the
  2D reactor as fallback and says so in the feed.
- `server/mia_core/autonomy/` — the mini sub-OS layer: adaptive machine
  profile/backends (`profile.py`), declarative conditions, plan execution with
  verification/retry/rollback/journal (`planner.py`), persistent jobs and rules
  (`scheduler.py`), health watchdog (`health.py`), deterministic Slovenian
  system-command router (`intents.py`), shared facade (`service.py`) and the
  `mia-auto` CLI. HUD: `/hud/autonomy.html`; API: `/api/autonomy/*`.

## Commands

```bash
# tests (stdlib unittest; no pytest needed)
python3 -m unittest discover -s tests -v

# learning core
python3 -c "import sys; sys.path.insert(0,'server'); import mia_core; print(mia_core.__version__)"
./skills/mia-companion/bin/mia-learn doctor --json
./skills/mia-companion/bin/mia-learn brief "odpri google"
./skills/mia-companion/bin/mia-skill validate
./skills/mia-companion/bin/mia-ctl doctor --json
./skills/mia-companion/bin/mia-learn capabilities --refresh
./skills/mia-companion/bin/mia-auto profile --json
./skills/mia-companion/bin/mia-auto status
./skills/mia-companion/bin/mia-auto health --json
./skills/mia-companion/bin/mia-auto route "opomni me čez 5 minut, da pijem vodo"
./skills/mia-companion/bin/mia-auto jobs add "test" --every 3600 --plan '{"steps":[{"kind":"python","action":"noop"}]}'
./skills/mia-companion/bin/mia-auto tasks list
server/scripts/fetch-avatar-assets.sh
python3 server/scripts/calibrate_voice.py --help

# installer / runtime
./install.sh --yes
./start-mia.sh
./stop-mia.sh --status
./update.sh
```

The development container does **not** have fastapi/torch/requests/PyYAML.
Do not import `server/server.py` in tests; test pure modules and subprocesses.
`mia_core` must stay stdlib-only.

## Architecture facts

- Voice/chat turns go through `server/server.py` → Hermes Sessions API.
- A turn is routed by `mia_core/brain.py::classify_brain`: explicit actions,
  live-data questions, URLs and paths go to Hermes; casual chat goes to the
  optional fast chat model (`server/chat_brain.py`, OpenAI-compatible
  llama-server on `llm.chat.base_url`). The deterministic
  `autonomy/intents.py` router still runs first. If the chat model is off,
  unreachable or answers `[[AGENT]]`, the turn falls back to Hermes.

- Before a turn, `LEARNING.brief(transcript)` is prepended to the payload.
- After a turn, `LEARNING.record_turn(...)` writes an episode; successful
  tool-using episodes become recipes, failures become anti-patterns.
- Short feedback phrases are handled deterministically in `_run_turn`
  (`detect_feedback`, `detect_remember`) before Hermes sees them.
- A background startup task mines habits, ingests
  `~/.local/state/mia/control-audit.jsonl` and refreshes the skill index every
  `auto_mine_interval_seconds` (default 900).
- Learning is fail-open: never let a DB/tree error break the voice loop.
- Autonomy shares `LEARNING.store`; the server ticks the scheduler every
  `autonomy.interval_seconds` (30 s) and health every `health_interval` (300 s).
  `mia-auto daemon` is the headless equivalent.
- The deterministic router in `autonomy/intents.py` runs before Hermes in both
  `/api/chat` and the voice turn; unmatched text always falls through to the
  agent.
- Plan steps are argv lists executed through `mia-ctl`; `--yes` is appended only
  after a real confirmation or for a user-created automation. Destructive plans
  raise `NeedsConfirmation` otherwise.

## Conventions

- Code comments only for non-obvious invariants/trade-offs; no changelog
  comments.
- Learning package: no third-party imports (PyYAML optional, with a fallback
  parser in `knowledge.py`/`config.py`).
- Skill files: one domain per child skill; `SKILL.md` < ~450 lines; details in
  `references/`; front matter `name`, `description`, `parents`, `children`,
  `tags`, `capabilities`.
- `mia-ctl`: argument lists only (never `shell=True`); policy first; audit
  every call; destructive actions need `--yes`.
- Secrets: never store/speak them; `mia_core/privacy.py` is a safety net.

## Tests

- `tests/test_mia_core.py` — store, privacy, recipes, habits, context, skill
  tree, integration helpers, CLI.
- `tests/test_mia_ctl.py` — headless subprocess tests: policy, audit, dry-run,
  files, protected PIDs, service allowlist, power confirmation.
- `tests/test_capabilities.py` — catalog, detection, confirmation, learned.
- `tests/test_voice_calibration.py` — strict wake, calibration state machine,
  Google answer/show split (numpy-dependent tests skip if numpy is absent).
- `tests/test_avatar.py` — Slovenian viseme timeline, tags/moods on the PCM
  path, model-fetch and HUD wiring contracts.
- `tests/test_autonomy.py` — profile/metrics, planner verification/retries/
  rollback/confirmation, scheduler edge triggers and events, health, alerts,
  intent router, service confirmations and `mia-auto` CLI.
- `tests/test_brain_router.py` — chat-vs-agent routing and chat-brain gating
  (no network: the `requests` import is lazy).
- Keep tests hermetic: use `tempfile`, set `HOME`/`XDG_*` for `mia-ctl`.

## Known pitfalls (hard-won)

- The repository was cloned shallow; use `git fetch --unshallow` before
  history-dependent operations.
- `server/server.py` imports heavy deps; only `py_compile` it in this container.
- Large heredocs in the terminal tool can be silently truncated; use the file
  editor or split files.
- `LearningCore` accepts either a full server config (with a `learning:` block)
  or a flat learning config; keep both paths working.
- `mia-learn`/`mia-skill` find the repo via `MIA_HOME`, then
  `~/.config/mia/home`, then by walking up from the script.
- `install.sh` installs skills into `$HERMES_HOME/skills`; `uninstall.sh` is
  allowed to remove only `~/.hermes/skills/mia-*`, never other Hermes data.
- The HUD `openView()` treats paths starting with `/hud/` as local pages;
  everything else goes through the dashboard TLS proxy on :9443.
- Strict wake defaults to true; `followup_seconds` is ignored in strict mode.
- Only verified episodes (or user-confirmed) become recipes. Do not relax this
  without a deliberate migration.
- `server/logs/settings.json` is runtime state; do not commit it.
- Plans are executable state: never run `privacy.redact_obj()` over a plan in
  place (it corrupts argv). Redact audit/output only.
- Event rules must baseline on first observation; otherwise a rule fires just
  because Mia started. `normalize_trigger()` uses the `__unset__` sentinel.
- A condition rule is edge-triggered (`armed`/`since`); do not turn it into a
  level trigger or every tick will repeat the action.
- `mia-ctl net firewall` uses `dest` `fw_action` because `action` is already
  the subcommand name; keep that split.
- Avatar speech must carry a viseme timeline (`avatar_speech`) before the
  sentence PCM; `playChunk()` has only a 60 ms lookahead and no timestamps, so
  never assume the client can infer phonemes from audio.
- Slovenian lip sync is phoneme-driven (`espeak-ng` → Oculus 15 visemes) and
  scaled to the actual sentence duration; HeadAudio is only a fallback/hybrid
  refinement, not the primary source.
- Do not add random gestures or a webcam-style "idle loop"; the behaviour
  director must gate gaze/gesture/emotion on state, speech stress and user
  intent. This is the difference between premium and robotic.
- Gestures are procedural full-body tracks (`ACTIONS` in `motion.js`), not
  mocap clips. Each action is a list of key poses on world axes per bone; the
  runtime converts them to local axes against the current parent world
  quaternion and premultiplies them onto the idle pose. Keep every action's
  first and last key at rest (`{}`), otherwise it snaps.
- `_restoreBase()` must run before every `mixer.update()` and `_cacheBase()`
  right after it. The cache is the last mixer output, not the GLB bind pose:
  three.js can skip writing tracks for a frame at a clip loop boundary, and
  restoring the bind pose there makes the avatar snap to the T-pose every loop
  (the "poskakuje" bug). Caching before `_applyPose()` also stops procedural
  deltas from accumulating.
- `loadIdle()` strips non-quaternion tracks. Position tracks would move the rig
  to the idle GLB's own rest height, and scale tracks would overwrite the
  body-shape bone scales every frame; the runtime owns position and scale.
- Do not write `bone.rotation.*` directly for gaze/sway/gesture. Build a pose
  map and let `_applyPose()` compose it, or the idle clip and actions fight.
- Hair styles: the GLB meshes are listed first, then the 10 procedural wigs
  from `HAIR_STYLES`. Procedural wigs are stylised geometry attached to the
  Head bone, not simulated hair; `HAIR_LOOKS` only scales them. Do not rebuild
  a wig per frame — `_buildHair()` caches by style id and only recolours.
- Garments are authored in world space from the current skeleton and then
  re-parented to a bone (`_attachToBone`), so they follow that bone. Rebuild
  them when the accessory, colour, length, robot flags or body-shape sliders
  change; `_accessoryKey` covers that. They are props, not cloth simulation.
- Characters are appearance bundles on one GLB (`characters.js`). Applying a
  character must strip `label`/`note` before merging into the config; the
  Python validator drops unknown keys anyway, but the HUD would keep them.
- The sample GLB skins only the torso in `Wolf3D_Body`: arms live in the top
  mesh, legs in the bottom mesh, feet in the footwear mesh. Never hide those
  meshes to mean "off" — a limb disappears. `_setBare()` keeps the geometry and
  swaps in a skin-tone material without the fabric map, so "brez oblačil" is a
  body shell rather than a separate nude mesh.
- `BODY_SHAPES` and the shape sliders scale the rig's existing bones (Head,
  Neck, Shoulders, Hips, arms, legs, hands, feet). They are proportion controls,
  not a different body mesh; keep the ranges modest so joints do not tear.
- Avatar models are not committed. `server/hud/avatar/models/*.glb` is ignored;
  use `fetch-avatar-assets.sh` or `install.sh --with-avatar`. Keep the
  `ASSET_LICENSE` provenance in models/README.md.
- The HUD avatar uses `/hud/avatar/vendor/three` (vendored, no CDN) and an
  import map; keep `/hud` self-contained for offline use.
- `avatar_speech` must precede the binary PCM of the same sentence; the HUD
  anchors visemes to `window.MiaAudio.delay()`/playhead. Do not reorder.
- Capabilities live in `server/mia_core/capabilities.py`; adding an item means
  also wiring `mark_learned()` if it has a `mia-ctl` action.
- Never commit `server/config/server.yaml`, `server/logs/`, `server/voices/`,
  `server/certs/` or `.env` files (see `.gitignore`).

## Where to extend

- New control command: `mia-ctl` `build_parser()` + `dispatch()` + test.
- New skill: create `skills/<name>/SKILL.md`, add to `skills/tree.yaml` and
  the parent's `children`, run `mia-skill validate`.
- New brain route: add verbs/live-data words to `mia_core/brain.py`, keep
  `classify_brain` conservative (unknown → chat), and add a case to
  `tests/test_brain_router.py`. The chat client lives in `server/chat_brain.py`.
- New learning signal: add to `integration.py` (pure helpers) and wire it in
  `server.py`; add a unit test.
- New HUD view: add a panel in `server/hud/index.html` and a page under
  `server/hud/`; protect it with the existing token middleware.
- New avatar setting: add it to `server/hud/avatar/presets.js` (`DEFAULTS`,
  `SCHEMA`, optionally a preset group), mirror the default and its
  colour/bool/string/range in `server/avatar_config.py`, and use it in
  `avatar.js`; `tests/test_avatar.py` enforces parity (including that every
  default has a validator). `/hud/avatar.html` is generated from `SCHEMA`, so
  no per-field HTML is needed.
- New avatar action: add an entry to `ACTIONS` in
  `server/hud/avatar/motion.js` (label, group, dur, keys from t=0 to t=1 at
  rest), optionally an alias in `ACTION_ALIASES`; it appears automatically in
  the LIK page chips. Add it to the required-move test if it is a core move.
- New wig: add it to `HAIR_STYLES` in `presets.js` and build it in
  `hair.js` (`buildHair` switch). It is then listed by `hairStyles()`.
- New garment: add it to `ACCESSORY_STYLES` in `presets.js`, build it in
  `garments.js` (`buildAccessory` switch), and attach to an existing bone.
- New character: add a full appearance bundle to `characters.js` (keys must
  exist in `DEFAULTS`; `label`/`note` are metadata). It is picked up by
  `PRESETS.character`, the schema select and the chips.
- New autonomy capability: add it to `autonomy/profile.py` BACKEND_CHAINS +
  READINESS_GROUPS, to `capabilities.py` CATALOG/mark_learned, and (if it has a
  `mia-ctl` verb) to the `mia-ctl` parser + dispatch + `verify_result`.
- New plan step kind: `planner.STEP_KINDS`, `sanitize_plan` and
  `_execute_step`; add a test.
- New trigger: `scheduler.TRIGGER_KINDS`, `normalize_trigger`, `_is_due` and
  `next_run`; keep condition rules edge-triggered.
- New natural command: add an anchored rule to `autonomy/intents.py` and a
  handler in `autonomy/service.py`; add it to the intent test table.
- 3D avatar work: read `docs/AVATAR.md` first. The decision is Tier A
  (TalkingHead/Three.js + licensed GLB) now, Audio2Face optional, MetaHuman +
  Pixel Streaming later. Keep the current `#reactor` ring as a fallback; vendor
  the runtime and assets locally (no CDN), record every asset licence, and add
  `avatar_speech`/`avatar_state` to the existing voice WebSocket rather than a
  second channel.
