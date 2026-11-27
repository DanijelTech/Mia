# Support

Thanks for using Mia. This page tells you where to ask what, so the right people
can help quickly.

## Before you ask

1. Read [`README.md`](README.md) and the relevant guide in [`docs/en/`](docs/en/)
   (or [`docs/`](docs/) in Slovenian).
2. Run the health checks:

   ```bash
   ./stop-mia.sh --status
   ./start-mia.sh --version
   ./skills/mia-companion/bin/mia-learn doctor --json
   ./skills/mia-companion/bin/mia-ctl doctor --json
   ```

3. Search existing issues and discussions — someone may have hit the same
   hardware, model or browser problem.

## Where to go

| I need… | Where |
|---|---|
| A question, idea, show-and-tell, or "how do I…" | [GitHub Discussions](https://github.com/DanijelTech/Mia/discussions) |
| A reproducible bug | [Bug report](https://github.com/DanijelTech/Mia/issues/new?template=bug_report.yml) |
| A new feature or integration | [Feature request](https://github.com/DanijelTech/Mia/issues/new?template=feature_request.yml) |
| An accessibility barrier | [Accessibility issue](https://github.com/DanijelTech/Mia/issues/new?template=accessibility.yml) |
| A security vulnerability | **Never a public issue** — use [private vulnerability reporting](https://github.com/DanijelTech/Mia/security/advisories/new) and see [`SECURITY.md`](SECURITY.md) |
| A code of conduct incident | Private report via the channel in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) |
| A translation correction | [Bug report](https://github.com/DanijelTech/Mia/issues/new?template=bug_report.yml) with the `translation` label, or a PR |

## What to include in a bug report

- Mia version (`./start-mia.sh --version` or `/api/version`)
- install mode (`system`, `user`, manual venv) and OS/desktop
- the exact voice or typed command, and the reply/error
- relevant lines from `server/logs/latency.jsonl`, `server/logs/mia.out` or
  `journalctl --user -u mia-voice -n 50`
- **redact** tokens, API keys, e-mail addresses, IP addresses, paths and voice
  samples before posting

## Response expectations

Mia is a volunteer, local-first project. Maintainers aim to triage new issues
within a few days, but there is no paid support SLA. A clear reproduction,
version and logs are the fastest way to get a fix.

## Commercial / private support

There is no paid support offering. If you need a custom deployment, open a
Discussion describing the scope; the community may be able to help, and a
maintainer can say whether it fits the roadmap.
