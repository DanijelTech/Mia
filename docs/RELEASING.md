# Izdajanje Mie

> Angleška različica: [docs/en/RELEASING.md](en/RELEASING.md)

Mia follows semantic versioning (`MAJOR.MINOR.PATCH`). The single source of
truth is [`VERSION`](../VERSION); `mia_core.__version__`, `/api/version`, the
HUD badge, `./install.sh --version`, `./start-mia.sh --version`,
`./stop-mia.sh --version`, `./update.sh --version`,
`./uninstall.sh --version` and `./build-package.sh --version` all read it.

## Release checklist

1. **Bump** `VERSION` (e.g. `1.1.0` → `1.2.0`).
2. **Changelog**: add a `## [x.y.z] — YYYY-MM-DD` section to
   [`CHANGELOG.md`](../CHANGELOG.md) with Added / Changed / Fixed.
3. **Docs**: update `README.md`, `README.sl.md`, `docs/` and `docs/en/` for
   user-visible behaviour, and `AGENTS.md` for new architecture facts or
   pitfalls.
4. **Verify**:

   ```bash
   python3 -m unittest discover -s tests -v
   python3 -m ruff check --select F,E9,B server client worker hermes-plugin tests
   bash -n install.sh start-mia.sh stop-mia.sh update.sh uninstall.sh build-package.sh
   ./start-mia.sh --version
   ```

5. **Package**: `./build-package.sh` produces
   `dist/mia-<version>.tar.gz` (no voices, certs, logs or `server.yaml`).
6. **Commit**: `git add -A && git commit -m "release: vX.Y.Z"`.
7. **Tag**: `git tag -a vX.Y.Z -m "Mia vX.Y.Z" && git push origin main --tags`.
8. **Install test** on a clean machine: `sudo ./install.sh --yes --open`,
   open the HUD, run one voice turn, `./stop-mia.sh --status`, then
   `./uninstall.sh --dry-run`.
9. **Announce** the version, the migration notes (if any) and the tested
   hardware/OS in the release description.

## Version policy

- `MAJOR` — incompatible config, API, database or control-policy changes.
- `MINOR` — new features, new tools/skills, new HUD pages, new config keys.
- `PATCH` — bug fixes, documentation, performance and security fixes that do
  not change the interface.

The installer records the version in the install manifest, so `uninstall.sh`
and support can tell which release created which files.
