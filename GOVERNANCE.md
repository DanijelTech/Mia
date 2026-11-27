# Governance

Mia is an open, local-first project. This document explains who decides what,
how contributions are reviewed, and how you can become a maintainer.

## Principles

1. **Local-first and private by default.** No feature may silently send voice,
   memory or machine data to a cloud service.
2. **Latency is a feature.** A change that makes the voice loop slower needs a
   measured justification.
3. **Explainable behaviour.** Deterministic commands, memory and plans must be
   reviewable; no hidden prompt magic.
4. **Small, tested changes.** A PR should be reviewable in one sitting.
5. **Respect.** The [Code of Conduct](CODE_OF_CONDUCT.md) applies everywhere.

## Roles

| Role | What they do |
|---|---|
| **Users** | Report bugs, request features, test releases, improve docs. |
| **Contributors** | Send PRs, review code, triage issues, translate docs. |
| **Reviewers** | Regular contributors trusted to review a subsystem (voice, HUD, learning, autonomy, installers). |
| **Maintainers** | Merge to `main`, cut releases, manage security reports and repository settings. Current maintainer: [@DanijelTech](https://github.com/DanijelTech). |

## Decision making

- **Lazy consensus**: a PR or proposal is accepted when it has no blocking
  review and CI is green. Silence is not consent for security, data-format or
  breaking changes.
- **Subsystem ownership**: the reviewer closest to the code decides style and
  implementation details; the maintainer decides scope and releases.
- **Breaking changes** (config, API, database, control policy) need an issue,
  a migration note and a `MAJOR` version.
- **Security** reports are handled privately; the maintainer coordinates the
  fix, release and disclosure.
- **Disagreement**: discuss in the issue/PR; if no consensus, the maintainer
  makes the call and records the reason.

## Review and merge

1. Open a PR using the template; link the issue.
2. CI must pass (`tests`, `ruff`, `compile`, `shell`, version check).
3. At least one reviewer approves; the maintainer merges with a squash or a
   clean commit series.
4. User-visible behaviour updates docs (`README.md`, `README.sl.md`, `docs/`,
   `docs/en/`), `CHANGELOG.md` and `VERSION` when releasing.
5. No secrets, local state or generated files in the diff.

## Becoming a maintainer

Consistent, respectful contributors who review and land several changes may be
invited as reviewers. A reviewer who sustains review and release work may be
invited as a maintainer by the current maintainer, with a public note in the
repository. There is no fixed quota and no payment.

## Releases

Mia uses semantic versioning and tags every release (`vX.Y.Z`). The process is
in [`docs/RELEASING.md`](docs/RELEASING.md). Release notes come from
[`CHANGELOG.md`](CHANGELOG.md); the installer manifest records the version.

## Roadmap and priorities

The public roadmap is [`ROADMAP.md`](ROADMAP.md). It is a direction, not a
promise; security, data-loss and accessibility blockers take priority over new
features.
