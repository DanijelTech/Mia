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
- Capabilities live in `server/mia_core/capabilities.py`; adding an item means
  also wiring `mark_learned()` if it has a `mia-ctl` action.
- Never commit `server/config/server.yaml`, `server/logs/`, `server/voices/`,
  `server/certs/` or `.env` files (see `.gitignore`).

## Where to extend

- New control command: `mia-ctl` `build_parser()` + `dispatch()` + test.
- New skill: create `skills/<name>/SKILL.md`, add to `skills/tree.yaml` and
  the parent's `children`, run `mia-skill validate`.
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
