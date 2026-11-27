# Community & growth playbook

> Slovenian version: [../COMMUNITY.md](../COMMUNITY.md)

This is the practical checklist for making Mia easy to discover, trust and
contribute to. It is written for the maintainer but is public so contributors
can see how the project is run.

## 1. Community standards checklist

| GitHub requirement | File in this repo |
|---|---|
| README | [`README.md`](../../README.md) (English), [`README.sl.md`](../../README.sl.md) (Slovenian) |
| Code of conduct | [`CODE_OF_CONDUCT.md`](../../CODE_OF_CONDUCT.md) |
| Contributing | [`CONTRIBUTING.md`](../../CONTRIBUTING.md) |
| License | [`LICENSE`](../../LICENSE) (MIT) |
| Security policy | [`SECURITY.md`](../../SECURITY.md) |
| Issue templates | [`.github/ISSUE_TEMPLATE/`](../../.github/ISSUE_TEMPLATE/) |
| Pull request template | [`.github/pull_request_template.md`](../../.github/pull_request_template.md) |
| Additional community file | [`SUPPORT.md`](../../SUPPORT.md), [`GOVERNANCE.md`](../../GOVERNANCE.md), [`ROADMAP.md`](../../ROADMAP.md), [`ACCESSIBILITY.md`](../../ACCESSIBILITY.md) |
| Accessibility | [`ACCESSIBILITY.md`](../../ACCESSIBILITY.md) |

Keep these links in the README so a visitor can find them in one click.

## 2. Repository settings (GitHub UI)

Open **Settings** on `github.com/DanijelTech/Mia`:

- **About** (right sidebar → gear):
  - Description: `Local-first Slovenian/English voice assistant and Iron-Man HUD on Hermes Agent — offline STT/TTS, memory, autonomy, audited computer control.`
  - Website: your docs or demo URL (optional).
  - Topics: `voice-assistant`, `local-first`, `offline`, `slovenian`, `hermes-agent`,
    `whisper`, `piper-tts`, `llm`, `home-automation`, `privacy`, `accessibility`,
    `self-hosted`, `python`, `fastapi`, `hud`.
- **General → Features**: enable **Discussions** (questions, ideas, show-and-tell,
  polls), keep **Issues** enabled, disable **Wiki** unless you maintain it.
- **General → Pull requests**: enable *Allow squash merging* and *Automatically
  delete head branches*; disable merge commits if you prefer a linear history.
- **Branches → Branch protection** for `main`: require CI (`test (3.11)`,
  `test (3.12)`), require a pull request before merging, require approvals (1),
  dismiss stale approvals, require conversation resolution, block force pushes
  for everyone except the maintainer.
- **Code security**: enable **Private vulnerability reporting**, **Dependabot
  alerts** and **Secret scanning** (public repos), and Dependabot security
  updates.
- **Social preview**: upload `docs/images/hud-en.png` (Settings → General →
  Social preview) so shared links show the HUD.
- **Releases**: create a release from tag `v1.1.0`, paste the matching
  `CHANGELOG.md` section, and attach `dist/mia-1.1.0.tar.gz` from
  `./build-package.sh`.
- **Pin** an issue titled **“Start here: good first issues”** that links to
  [`ROADMAP.md`](../../ROADMAP.md) and the `good first issue` label.

## 3. Labels that make contribution easy

Create these labels (Settings → Labels) or let the issue templates apply them:

`bug`, `enhancement`, `documentation`, `translation`, `accessibility`,
`good first issue`, `help wanted`, `needs-triage`, `security`, `installer`,
`voice`, `hud`, `learning`, `autonomy`, `plugin`, `wontfix`.

Apply `good first issue` only to tasks with a clear file, expected result and
test command. A newcomer should be able to finish it in an evening.

## 4. Contributor funnel

1. **Discover**: README screenshot, a 30–60 s demo GIF/video, topics, release
   notes and one clear sentence about what Mia is.
2. **Trust**: local-first/privacy promise, tests, CI badge, security policy,
   versioning, changelog, licence.
3. **Try**: one-command install, offline package, `--dry-run`, health checks.
4. **Contribute**: good first issues, roadmap, issue templates, PR template,
   code of conduct, support guide.
5. **Stay**: review quickly, credit contributors in release notes, say thank
   you, and close stale issues with a reason.

## 5. Launch checklist (when you want attention)

- [ ] README has the English HUD screenshot and a 30–60 s demo.
- [ ] `v1.1.0` release exists with notes and the offline tarball.
- [ ] CI is green on `main`.
- [ ] At least 5 `good first issue` tasks exist.
- [ ] Discussions has a “Show your setup” and a “Q&A” category.
- [ ] Security policy and code of conduct are linked in the README.
- [ ] Post once, honestly, where local-first/voice/LLM people are:
      r/LocalLLaMA, r/selfhosted, r/slovenia, Hacker News “Show HN”,
      Lemmy/Mastodon, relevant awesome-lists. Do not spam; answer questions.
- [ ] Ask for specific help (“test the installer on Fedora”, “translate one HUD
      string”) rather than “please contribute”.
- [ ] After launch, publish a short “what we learned / what is next” update.

## 6. Accessibility and translations

- Every HUD string belongs in `server/hud/i18n.js`; every deterministic reply
  belongs in `server/mia_core/i18n.py`. The tests fail when a static string is
  missing.
- Accessibility barriers are bugs; use the Accessibility issue template and
  the `accessibility` label.
- A translation PR is welcome even if it is one string. Include a screenshot
  of the result in English and the source language.

## 7. Metrics to watch (not vanity metrics)

- time from issue to first human response,
- PRs merged per month and review latency,
- number of `good first issue` tasks completed by new contributors,
- test/CI pass rate,
- install success reports by OS/desktop,
- accessibility reports closed,
- number of active Discussions participants.

Stars are nice, but a project that answers issues and merges small PRs grows
faster than one that only asks for stars.
