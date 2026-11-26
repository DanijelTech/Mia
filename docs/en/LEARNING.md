# Learning, memory and the skill tree

Mia has a durable, queryable and explainable memory. Every accepted voice or
typed turn, every `mia-ctl` action and every user correction is stored locally.
From that data Mia derives **habits**, **recipes** and **anti-patterns** (things
that failed and must not be repeated).

- Database: `~/.local/state/mia/learning.db` (SQLite, WAL).
- Control audit: `~/.local/state/mia/control-audit.jsonl`.
- Skill tree: `skills/` (validated by `mia-skill validate`).

## The loop

```
observe → record → mine → recall → act → evaluate → update
```

1. **Automatic capture** — each accepted turn becomes an episode (request,
   response, tools, steps, outcome, duration, errors, entities). Each
   `mia-ctl` call is audited and ingested as a control episode. Rejected
   turns (wrong speaker, no wake word) are not recorded.
2. **Context injection** — before each turn the server prepends a bounded
   `[MIA SPOMIN …]` block with relevant habits, recipes, anti-patterns and
   preferences. Default limit: 1500 characters.
3. **Feedback** — short phrases (»tako je«, »ni prav«, »zapomni si postopek«)
   are handled deterministically on the previous episode. Longer corrections
   reach the agent, which must act and call `mia-learn feedback`.

## Habits, recipes, anti-patterns

- **Habit**: an entity repeated at least 3 times in 120 days; a 2-hour window
  with ≥35 % of occurrences becomes a routine; repeated adjacent intents
  become a sequence. Confidence decays when the habit stops.
- **Recipe**: a proven procedure with confidence
  `(success + 1) / (success + fail + 2) × saturation`. Matching is lexical:
  50 % Jaccard + 30 % containment + 20 % sequence ratio, threshold 0.52.
- **Anti-pattern**: what failed, why, and the fix. Created automatically from
  failures and manually with `mia-learn mistakes --add`.

## Commands

```bash
mia-learn status
mia-learn brief "open google"
mia-learn episodes --limit 20
mia-learn search "invoice"
mia-learn habits
mia-learn recipes
mia-learn mistakes
mia-learn facts
mia-learn remember --note "why this works"
mia-learn feedback --verdict negative --note "prefer Chrome"
mia-learn mine
mia-learn tree
mia-learn doctor
mia-learn export ~/backups/mia-learning.json
mia-learn backup ~/backups/mia-learning.db
mia-learn prune
```

Add `--json` for machine-readable output.

## Skill tree

```
mia-companion        persona, language, routing, safety
├── mia-desktop      windows, apps, input, screenshots, clipboard, power
├── mia-learning     episodes, habits, recipes, mistakes, feedback
├── mia-music        YouTube, history, favourite artists
├── mia-browser      search, HUD panels, browsing
├── mia-productivity kanban, cron, reading aloud
└── mia-diagnostics  health, logs, restart, capabilities
```

```bash
mia-skill tree
mia-skill list
mia-skill validate
mia-skill search "window"
mia-skill install "$HERMES_HOME"
```

`install.sh` installs the whole tree into the active `$HERMES_HOME/skills`.

## HUD

The **SPOMIN IN ZNANJE** panel shows counts and top habits. **ODPRI ZNANJE**
opens `/hud/learning.html`: overview, skill tree, habits, recipes, mistakes,
episode log with ✓/✗ feedback, search and manual entry forms.

## Configuration

`server/config/server.yaml`:

```yaml
learning:
  enabled: true
  db_path: "~/.local/state/mia/learning.db"
  auto_record: true
  auto_feedback: true
  auto_mine_interval_seconds: 900
  context:
    enabled: true
    max_chars: 1500
  retention:
    episodes_days: 400
  habits:
    min_evidence: 3
  recipes:
    match_threshold: 0.52
```

Environment overrides: `MIA_LEARNING_ENABLED`, `MIA_LEARNING_DB`,
`MIA_LEARNING_AUDIT`, `MIA_SKILLS_ROOT`, `MIA_LEARNING_CONTEXT_MAX_CHARS`,
`MIA_LEARNING_MINE_INTERVAL`.

## Privacy and operations

- All text is redacted before storage (keys, tokens, passwords, private keys,
  e-mail, phone/card-like numbers). This is a safety net, not permission to
  store secrets.
- Retention: 400 days / 200 000 episodes, 180 days of events; stale habits
  decay away.
- Backups: `mia-learn backup` (SQLite) or `mia-learn export` (portable JSON);
  restore with `mia-learn import`.
- The learning store fails open: a broken DB never takes the voice loop down.

## Limits

- Recipe matching is lexical, not semantic; clear requests and entity metadata
  matter.
- A habit needs at least 3 occurrences.
- The local model must honour the injected brief; the Hermes system prompt and
  the skill tree are aligned for that.
