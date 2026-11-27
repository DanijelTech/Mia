# Contributing to Mia

Mia is a local-first voice assistant: correctness, latency and privacy matter
more than clever abstractions. Small, tested, explainable changes are welcome.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). For
questions and design discussion use [Discussions](https://github.com/DanijelTech/Mia/discussions);
for a reproducible bug use the [issue templates](https://github.com/DanijelTech/Mia/issues/new/choose).
See [SUPPORT.md](SUPPORT.md), [GOVERNANCE.md](GOVERNANCE.md) and
[ROADMAP.md](ROADMAP.md).

## Find something to work on

- Issues labelled **good first issue**, **help wanted**, **documentation**,
  **translation** or **accessibility**.
- The [roadmap](ROADMAP.md) “good first contributions” list.
- A command you use that has no test; a HUD string without an English pair; an
  installer/desktop combination that is not documented.

For a large change or a new dependency, open a Discussion or an issue first so
we can agree on scope before you invest a weekend.

## Before you start

- Read [`AGENTS.md`](AGENTS.md) — it documents the architecture, the hard-won
  pitfalls and where to extend each layer.
- Keep `mia_core` stdlib-only; it runs inside the server, CLIs and tests.
- Do not commit `server/config/server.yaml`, `server/logs/`, `server/voices/`,
  `server/certs/` or `.env` files.
- Never add a second model to the examples; the default is one llama-server.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m ruff check --select F,E9,B server client worker hermes-plugin tests
bash -n install.sh start-mia.sh stop-mia.sh update.sh uninstall.sh
node --check <(extract inline scripts)   # or use tests/test_hud_boot.py
```

The development container may not have FastAPI/torch/RealtimeSTT. Do not import
`server/server.py` in tests; test pure modules and subprocesses.

## Adding things

- **A control command**: `mia-ctl` `build_parser()` + `dispatch()` + a
  `tests/test_mia_ctl.py` case; add the capability to
  `mia_core/capabilities.py`.
- **A skill**: `skills/<name>/SKILL.md`, add it to `skills/tree.yaml` and the
  parent's `children`, run `mia-skill validate`.
- **A brain route**: `mia_core/brain.py`, keep `classify_brain` conservative
  (unknown → chat), add a `tests/test_brain_router.py` case.
- **A learning signal**: pure helper in `mia_core/integration.py`, wire it in
  `server.py`, add a unit test.
- **A HUD string**: add it to `server/hud/i18n.js` DICT; the HUD i18n test
  fails otherwise.
- **A deterministic reply**: add an exact/pattern entry to
  `server/mia_core/i18n.py`; `tests/test_i18n.py` covers it.
- **A plugin tool**: add the schema and handler, and make sure
  `register(ctx)` registers it; `tests/test_plugin_registration.py` fails
  otherwise.

## Pull requests

1. Fork the repository and create a topic branch (`fix/wake-word`, `docs/english`,
   `feat/tts-provider`). Do not work on `main`.
2. Make one focused change; add or update a test for every behaviour change.
3. Run the full checks locally:

   ```bash
   make test
   make lint
   make shellcheck
   make compile
   ```

4. Fill in the PR template, link the issue, and include screenshots for HUD
   changes. The PR template checklist is not decoration: CI and review use it.
5. A maintainer/reviewer approves and merges. Keep the branch up to date if
   `main` moved; do not force-push someone else's branch.

Rules of thumb:

- Update `README.md`, `README.sl.md`, `docs/` or `docs/en/` for user-visible
  behaviour, and `AGENTS.md` for architecture facts or pitfalls.
- Bump [`VERSION`](VERSION) and add a `CHANGELOG.md` entry for a release; see
  [`docs/RELEASING.md`](docs/RELEASING.md).
- Never commit secrets, tokens, local paths, IPs, voice samples or
  `server/config/server.yaml`. See [`SECURITY.md`](SECURITY.md).
- HUD changes: add both SLO and ENG strings (`server/hud/i18n.js`), test
  keyboard/focus, and include a screenshot.
- Accessibility: a barrier is a bug; use the Accessibility issue template and
  the `accessibility` label.

## Recognition

Contributors are credited in release notes. Consistent reviewers may be invited
to become reviewers or maintainers; see [GOVERNANCE.md](GOVERNANCE.md).

## Style

- Comments only for non-obvious invariants, workarounds or trade-offs; no
  changelog comments.
- Argument lists for subprocesses, never `shell=True`.
- Fail open for learning/UI helpers; fail clearly for security and control.
