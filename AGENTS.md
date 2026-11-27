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
- `server/hud/background.html` — the "V OZADJU" page: what Mia runs in the
  background (media windows, HUD panels, stack services, autonomy jobs), manual
  closing/stopping and the manual-override switch.
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
- The chat model gets a capability summary and a "no steps, return `[[AGENT]]`"
  prompt. `_hermes_turn` prepends `hermes.system_prompt_extra` (default
  tools/paths brief) and the last two chat turns; agent replies are written
  back with `CHAT.note()` so the next chat turn has context.

- `tts.provider: http` defaults to a Piper fallback (`tts.fallback`, or
  `tts.http.fallback_piper`). If Maya1/Gepard is down or still loading, the
  wrapper speaks with Piper instead of failing the turn; set `tts.fallback: ""`
  to disable. `start-mia.sh` passes `--fallback-piper` to the manual Maya1
  service too.
- The `mia-tts` systemd unit is generated at install time. Maya1 voice comes
  from `tts.maya1.voice` and `CUDA_VISIBLE_DEVICES` from `tts.maya1.gpu_id`;
  re-run `./install.sh --tts-engine maya1` after changing them, or the unit
  keeps the old (default male) voice. Check `/health` on :8770 for
  `engine`/`voice`; `piper` there means the fallback is speaking.

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
- `tests/test_autonomy.py` — profile/metrics, planner verification/retries/
  rollback/confirmation, scheduler edge triggers and events, health, alerts,
  intent router, service confirmations and `mia-auto` CLI.
- `tests/test_brain_router.py` — chat-vs-agent routing and chat-brain gating
  (no network: the `requests` import is lazy).
- `tests/test_tts_fallback.py` — HTTP→Piper TTS fallback (skips without numpy).
- Keep tests hermetic: use `tempfile`, set `HOME`/`XDG_*` for `mia-ctl`.

## Known pitfalls (hard-won)

- The repository was cloned shallow; use `git fetch --unshallow` before
  history-dependent operations.
- The 3D avatar layer (Three.js runtime, wardrobe, visemes, `/api/avatar/*`,
  `avatar_config.py`, `avatar_visemes.py`) was removed on purpose — it was
  CPU/GPU load the user does not want. Do not reintroduce it; the HUD centre
  is the `#reactor` ring only. `strip_speech_tags()` still removes
  `[mood:…]`/`[gesture:…]` tags before TTS.
- `manual_override` (`server/logs/ui-state.json`) keeps desktop windows when a
  new track starts (`_stop_all_media(auto=True)`); the HUD panel is still
  replaced so two panels never play at once. Explicit stops,
  `/api/music/stop` and `/api/background/close*` must pass `auto=False`,
  otherwise the user cannot stop playback while the override is on.
- Window closing has three entry points that must stay in sync: `mia-close`
  (shell, registry + title fallback), `mia-ctl media close [pattern…]`
  (audited, for the agent/plans) and `media.close` in `autonomy/intents.py`.
  All of them need `xdotool` on Linux; `/api/background` returns a `tools`
  block (xdotool/wmctrl/browser/mia-open/mia-close/DISPLAY/registry) and the
  HUD "V OZADJU" page shows it, so a missing tool is visible instead of silent.
- `/api/background/close` closes a window only when its id is in Mia's
  `~/.cache/mia-windows` registry; never accept an arbitrary window id.
  Stack services are stopped through their configured pidfile (or systemd
  unit) — never by port or process name.
- Media control is deterministic and must stay so: `media_stop_request()`
  (pure, in `integration.py`) runs before the music parser and before the
  autonomy router in both `/api/chat` and the voice turn. Without it,
  »ustavi youtube« and »zapri vsa okna youtube« contain a music word, the
  play parser returned `''` ("play a favourite") and the user got yet another
  song instead of silence; »ugasni glasbo« even reached the power-shutdown
  rule. `music_play_request()` now returns `None` when no play verb matches —
  do not loosen that back.
- `mia-open`/`mia-close` must be resolved with `find_tool()`, not bare names:
  systemd units do not inherit `~/.local/bin` from the login shell, so a bare
  `mia-close` raised FileNotFoundError and was swallowed — windows opened but
  never closed. `mia-close` takes several URL patterns and falls back to
  browser window titles (for windows opened by `xdg-open`); without `xdotool`
  it exits 3 with a message. A failed `windowclose` keeps its registry entry.
- `server/hud/index.html::dismissPanel()` blanks the iframe/video source before
  the 700 ms exit animation, otherwise two panels overlap audibly.
- `start-mia.sh` health means `http_ready` (HTTP status < 500), not "the port
  answers". llama-server binds early and returns 503 `Loading model` until the
  GGUF is loaded; a bare socket check reported "up" while the 12B model was
  still on disk, so the chat model was started on top of it, missed its
  timeout, and Hermes came up without a usable model (`run.failed` with empty
  `runtime.provider`/`model`). `port_open` only means "something listens — wait
  for it, never start a second server". Each background start writes an
  `==> <label> started` marker so failure hints quote the current run only.
  Exit code 3 = HUD is up but part of the stack is not ready.
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
- New autonomy capability: add it to `autonomy/profile.py` BACKEND_CHAINS +
  READINESS_GROUPS, to `capabilities.py` CATALOG/mark_learned, and (if it has a
  `mia-ctl` verb) to the `mia-ctl` parser + dispatch + `verify_result`.
- New plan step kind: `planner.STEP_KINDS`, `sanitize_plan` and
  `_execute_step`; add a test.
- New trigger: `scheduler.TRIGGER_KINDS`, `normalize_trigger`, `_is_due` and
  `next_run`; keep condition rules edge-triggered.
- New natural command: add an anchored rule to `autonomy/intents.py` and a
  handler in `autonomy/service.py`; add it to the intent test table.
