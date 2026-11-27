## What does this PR do?

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Type of change

- [ ] Bug fix
- [ ] New feature / capability
- [ ] Performance
- [ ] Security / privacy
- [ ] Accessibility
- [ ] Documentation / translation
- [ ] Installer / packaging / CI
- [ ] Refactor (no behaviour change)

## How was it tested?

<!-- Exact commands, hardware/OS, voice or typed commands, and the result. -->

```bash
python3 -m unittest discover -s tests -v
python3 -m ruff check server client worker hermes-plugin tests
bash -n install.sh start-mia.sh stop-mia.sh update.sh uninstall.sh
```

## Checklist

- [ ] The change is focused and reviewable.
- [ ] Tests cover the new behaviour (or I explained why no test is possible).
- [ ] `README.md`, `README.sl.md`, `docs/` or `docs/en/` updated for user-visible changes.
- [ ] `VERSION` and `CHANGELOG.md` updated for a release.
- [ ] No secrets, tokens, local paths, IPs, voice samples or `server/config/server.yaml` in the diff.
- [ ] Accessibility checked for HUD changes (keyboard, focus, labels, contrast).
- [ ] Translations added to `server/hud/i18n.js` and `server/mia_core/i18n.py` where relevant.
- [ ] `mia_core` remains stdlib-only; no new mandatory cloud dependency.
- [ ] I ran the tests above and they pass.

## Screenshots / recordings (HUD changes)

<!-- Drag an image here. Redact private data. -->

## Breaking changes / migration

<!-- Config, API, database or control-policy changes; otherwise write "None". -->
