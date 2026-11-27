# Roadmap

This is the public direction for Mia. It is intentionally short and honest: the
maintainer updates it after releases, and security/data-loss/accessibility
blockers always jump the queue. Dates are deliberately omitted.

## Now — make the local experience excellent

- [ ] **Voice latency**: measure end-of-speech → first audio on CPU-only and
      GPU boxes; publish a small benchmark table.
- [ ] **Bilingual polish**: English labels for all 119 capability rows and 19
      readiness rows; keep SLO/ENG tests green.
- [ ] **Accessibility**: high-contrast HUD theme, larger text, screen-reader
      pass, focus outlines and a skip-to-chat link.
- [ ] **Reliability**: end-to-end test on a clean Linux + systemd machine and a
      macOS launchd machine; document the tested hardware.
- [ ] **First-run experience**: one screen that explains the microphone, the
      token and the first voice command.

## Next — make it easy to extend

- [ ] **Plugin SDK**: a tiny template and test harness for a new Hermes tool.
- [ ] **Voice providers**: document a second local TTS/STT engine end to end,
      including a CPU-only fallback.
- [ ] **Skill tree**: add a community skill template and a `mia-skill new`
      scaffold.
- [ ] **Packaging**: signed/checksummed offline tarballs and a container image.
- [ ] **Observability**: a `/api/health` summary for the whole stack, with the
      same data as the HUD diagnostics panel.

## Later — make it a platform

- [ ] **Multi-user households**: separate voice profiles and memory scopes.
- [ ] **Remote GPU worker**: discovery, auth and failover for STT/TTS workers.
- [ ] **Mobile companion**: push-to-talk and notifications without opening the
      full HUD.
- [ ] **Plugin registry**: a curated list of community skills and plugins.
- [ ] **Translations**: community-maintained language packs beyond SLO/ENG.

## Good first contributions

These are small, well-scoped and useful:

- Fix a typo or an unclear sentence in `README.md`, `README.sl.md` or `docs/`.
- Add an English `label_en`/`how_en` pair for one capability row.
- Add a test for a command you use (see `tests/test_mia_ctl.py`).
- Improve a browser accessibility detail (focus ring, `aria-label`, contrast).
- Add a screenshot or a short recording of a working setup.
- Test the installer on your distro/desktop and report what worked.
- Add a new recipe or anti-pattern example to the docs.
- Translate one HUD string and add it to `server/hud/i18n.js` DICT.

Look for issues labelled **good first issue**, **help wanted**,
**documentation**, **accessibility** or **translation**. If an area is missing,
open a Discussion — a clear problem statement is already a contribution.

## How to influence the roadmap

Open a Discussion with the problem, who it affects, and what a good outcome
looks like. A concrete use case, logs and a proposed scope are more persuasive
than a large speculative design. See [`GOVERNANCE.md`](GOVERNANCE.md).
