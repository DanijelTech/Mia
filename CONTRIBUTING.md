# Contributing to Mia

Mia is a local-first voice assistant: correctness, latency and privacy matter
more than clever abstractions. Small, tested, explainable changes are welcome.

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

- One focused change per PR, with a test for every behaviour change.
- Update the relevant docs (`README.md`, `README.sl.md`, `docs/`,
  `docs/en/`) and `AGENTS.md` when behaviour or a pitfall changes.
- Bump [`VERSION`](VERSION) and add a `CHANGELOG.md` entry for a release; see
  [`docs/RELEASING.md`](docs/RELEASING.md).
- Run the full test suite before pushing.

## Style

- Comments only for non-obvious invariants, workarounds or trade-offs; no
  changelog comments.
- Argument lists for subprocesses, never `shell=True`.
- Fail open for learning/UI helpers; fail clearly for security and control.
