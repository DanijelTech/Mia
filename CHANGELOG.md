# Changelog

All notable changes to Mia are documented here. The version lives in
[`VERSION`](VERSION) and is exposed by `/api/version` and the HUD header.

## [1.1.0] — 2026-11-27

The "close the gaps" release: a full audit of the runtime, security, voice
pipeline, learning core, HUD, Hermes plugins and installers.

### Added

- **Bilingual deterministic replies** (`server/mia_core/i18n.py`): clock,
  date, weather, volume, media, Google, autonomy, calibration and health
  answers follow the HUD's SLO/ENG switch. English LLM prompts
  (`language_directive_en`, `system_prompt_extra_en`,
  `llm.chat.system_prompt_en`).
- **English natural language**: "Hey Mia …" greetings, English music/Google/
  weather/volume/reminder/screenshot commands, natural English clock
  ("seven oh five in the evening").
- **Streaming speech**: TTS PCM is forwarded chunk-by-chunk, long clauses are
  cut at a natural break, and the HUD uses a small jitter buffer.
- **Adaptive endpointing** (350–700 ms) and safer barge-in: cancel only on a
  completed utterance; a verified voice may interrupt without the wake word.
- **Optional acknowledgement** while the agent thinks
  (`hermes.ack_after_seconds`).
- **Version API**: `/api/version`, HUD version badge, `--version` on every
  script, `VERSION`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`,
  `docs/RELEASING.md` and the English HUD screenshot in the README.
- **Project tooling**: `pyproject.toml` (ruff/coverage), `Makefile`
  (test/lint/shellcheck/compile/package/version), `requirements.txt`,
  `requirements-optional.txt` and a GitHub Actions CI workflow.
- **Community standards**: `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  `SUPPORT.md`, `GOVERNANCE.md`, `ROADMAP.md`, `ACCESSIBILITY.md`, bug/feature/
  accessibility issue templates, a pull request template, and a
  `docs/COMMUNITY.md` + `docs/en/COMMUNITY.md` growth playbook.
- **Tests**: i18n, continuous/wake/adaptive endpoint, plugin registration,
  worker stats, nested destructive plans, undo sanitization, anti-pattern
  hit counting, pitch forwarding.

### Changed

- `README.md` and `README.sl.md` are now presentation-first: what Mia is, why
  she matters, what she can do, a day with her, a three-step start, docs and
  community. Deep architecture/setup detail lives in `docs/` and `docs/en/`.
- Removed third-party brand promotion and upstream comparison from the README;
  factual attribution moved to `CREDITS.md`.

### Fixed

- Empty `hermes-plugin/mia_learning/__init__.py` and
  `hermes-plugin/mia_autonomy/__init__.py` meant Hermes never registered the
  memory/system tools.
- WebSocket auth bypass for clients without an `Origin` header.
- Nested destructive plans could bypass confirmation; rollback `undo`
  commands could run outside the `mia-ctl` vocabulary.
- `mia_learning` music tools called `/api/learning/music/*` (404); they now use
  `/api/music/*` with `MIA_MUSIC_URL` override.
- TTS pitch getter did not reach the HTTP backend through `FallbackBackend`.
- Missing `import os` in `worker/worker_stats.py` and `client/client.py`.
- `mia-auto profile --json` rejected `--json` after the subcommand.
- Hardcoded host name in `/api/machines`; dashboard proxy port hardcoded in the
  HUD; stale TLS port and model-path handling in `start-mia.sh`; dashboard
  port overwrite and single TLS port in `stop-mia.sh`.
- FTS search now tries `AND` first and reindexes facts/habits; anti-pattern
  hits no longer increase on a later success.
- `return` inside a `finally` block in the continuous turn loop.
- Blocking machine/capability/learning probes moved off the event loop.
- Uninstaller no longer deletes local data when the install manifest is
  missing (requires `--force`).

## [1.0.0] — 2026-11-27

First professional, documented release of the local-first Mia stack:

- Hermes Agent voice pipeline, HUD, local Whisper/Piper, speaker gate,
  distance calibration.
- Learning core: SQLite episodes, habits, recipes, anti-patterns, facts,
  skill tree, capabilities, `mia-learn`.
- Autonomy layer: machine profile, plans, scheduler, rules, health,
  deterministic Slovenian command router, `mia-auto`.
- Audited `mia-ctl`, `mia-open`/`mia-close`, `mia-volume`, `mia-skill`.
- Hermes plugins `hud_display`, `mia_learning`, `mia_autonomy`.
- Installer, uninstaller, updater, offline package builder, systemd/launchd
  units, TLS HUD.
