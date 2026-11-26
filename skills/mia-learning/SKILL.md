---
name: mia-learning
description: "Mia's durable learning loop: record episodes, mine habits, reuse proven recipes, avoid known mistakes and apply explicit user feedback. Use whenever the user says remember/forget/correct, or before repeating a recurring task."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [learning, memory, habits, recipes, mistakes, feedback, sqlite]
capabilities: [record_episode, mine_habits, reuse_recipe, avoid_anti_pattern, apply_feedback, store_preference, inspect_memory]
---

# Mia learning

This skill turns "the agent has memory somewhere" into a deterministic loop:

```
observe → record → learn → recall → act → evaluate → update
```

The voice server runs most of it automatically. You are responsible for the
parts that need meaning.

## What is automatic

- Every accepted voice turn and typed chat is recorded as an **episode**
  (request, response, tools, outcome, duration, errors, entities).
- Every `mia-ctl` call is written to an audit log and ingested as an episode
  with `source=control`.
- Successful episodes that used tools/steps become **recipes**.
- Failed episodes become **anti-patterns** (what not to repeat).
- Every ~15 minutes a background job mines **habits** and refreshes the skill
  index.
- Before each turn the server injects a bounded `[MIA SPOMIN …]` brief with
  relevant habits, recipes and anti-patterns.

You do **not** need to record a turn again. Do not duplicate the same episode.

## Prefer the first-class tools

If the `mia_learning` Hermes plugin is installed, use its tools instead of the
shell — they are faster, typed and harder to get wrong:

| Tool | Use |
|---|---|
| `memory_brief(request)` | exact brief for a request |
| `memory_search(query)` | search episodes, recipes, mistakes, facts |
| `memory_feedback(verdict, note)` | ✓/✗ on the previous action |
| `memory_remember(note)` | save the last procedure as a recipe |
| `memory_fact(key, value)` | durable preference/person/project |
| `memory_mistake(symptom, cause, fix)` | anti-pattern with a fix |
| `memory_status()` | counts and last mining |
| `skill_tree(query)` | find the skill that owns a capability |

The `mia-learn` commands below are the fallback (and the admin surface for the
user).

## What you must do

### 1. Store meaning, not transcripts

When the user states a durable fact or preference:

```bash
mia-learn facts --set "pref.browser" "firefox"
mia-learn facts --set "pref.music.genre" "ex-yu rock"
mia-learn facts --set "project.current" "Mia"
mia-learn facts --set "person.ana" "sestra, rojstni dan 12. maj"
```

Keys are short and stable (`area.subject`). Values are one line. Never store
secrets, passwords, tokens or private keys.

### 2. Save a recipe when the *how* matters

If a task succeeded through a non-obvious sequence, force the recipe:

```bash
mia-learn remember --note "Chrome app-window closes reliably with mia-close; plain pkill leaks it"
```

If you are recording a new task from scratch:

```bash
mia-learn record \
  --request "odpri mi glasbo v ozadju" \
  --response "Evo šefe." \
  --source voice --intent music --outcome success \
  --step '{"action":"mia-open","args":["https://www.youtube.com/watch?v=..."]}' \
  --meta '{"entities":[{"kind":"artist","value":"Baja Mali Knindza"}]}'
```

### 3. Record a mistake explicitly when the user explains it

Automatic failure capture knows *that* it failed; only you know *why*:

```bash
mia-learn mistakes --add "okno se ne zapre s pkill" \
  --cause "Chrome posreduje --app okna v obstoječi proces" \
  --fix "uporabi mia-close <domain>" --severity high
```

### 4. Apply feedback

Short phrases are intercepted by the server and applied to the previous
episode. For longer corrections that reach you:

```bash
mia-learn feedback --verdict negative --note "raje odpri v Chromu, ne v Firefoxu"
mia-learn feedback --verdict positive --note "tako je prav"
```

### 5. Inspect before answering "se spomniš?"

```bash
mia-learn brief "kje sem pustil pogodbo"     # what the agent would see
mia-learn search "pogodba"                   # full-text search
mia-learn episodes --limit 20                # recent turns
mia-learn recipes --limit 20                 # proven procedures
mia-learn mistakes --limit 20                # what not to repeat
mia-learn habits --limit 20                  # inferred routines
```

## Command reference

| Command | Purpose |
|---|---|
| `mia-learn status` | enabled, DB stats, skill summary, last mining |
| `mia-learn brief "request"` | exact memory brief for that request |
| `mia-learn episodes --limit N` | recent episodes (✓/✗/partial) |
| `mia-learn search "q"` | FTS across episodes, recipes, mistakes, facts |
| `mia-learn recipes` | proven procedures with confidence |
| `mia-learn recipes --show ID` | full steps of one recipe |
| `mia-learn recipes --add "title" --step "..."` | add a manual recipe |
| `mia-learn mistakes` | anti-patterns and fixes |
| `mia-learn habits` | inferred preferences and routines |
| `mia-learn habits --pin KEY` | pin a habit so decay never removes it |
| `mia-learn facts` | known preferences and system facts |
| `mia-learn remember --note "..."` | force the last episode into a recipe |
| `mia-learn feedback --verdict negative --note "..."` | correct the last episode |
| `mia-learn mine` | run habit mining + audit ingest now |
| `mia-learn sysinfo` | store the machine inventory as facts |
| `mia-learn tree` | skill tree (or `mia-skill tree`) |
| `mia-learn doctor` | DB + tree + tool availability |
| `mia-learn export FILE` / `import FILE` | backup / restore memory |
| `mia-learn prune` | apply retention policy |

Add `--json` for machine-readable output.

## How recipes are matched

- Text is normalised (lowercase, diacritics removed, filler words dropped).
- Score = 50 % Jaccard + 30 % containment + 20 % sequence ratio, plus an exact
  key match.
- Default threshold 0.52; the top 2 matches go into the brief.
- Confidence grows with successes and shrinks with failures:
  `rate × saturation`, so one lucky success is not trusted blindly.
- If a recipe fails, do not keep retrying it. Try a different approach and
  record the failure; the anti-pattern will warn future turns.

## How habits are inferred

- **Entity preference**: an app, domain, artist, path or query repeated at
  least 3 times in the last 120 days.
- **Routine**: the same subject concentrated in a 2-hour window (e.g. "music
  usually in the evening"), if that window holds ≥35 % of occurrences.
- **Sequence**: two intents repeated within 20 minutes at least 3 times
  (e.g. "music → volume").
- Confidence decays when a habit stops appearing (after 45 days), so stale
  habits disappear instead of misleading the agent.

## Rules

1. **Do not ask twice.** If the brief or a fact already answers it, use it.
2. **Prefer the proven recipe** over inventing a new sequence.
3. **Never repeat a listed anti-pattern.** Read the fix and use it.
4. **One correction, one update.** After the user corrects you, store the new
   method and follow it.
5. **Privacy first.** Redaction is a safety net, not permission to store
   secrets. Do not record clipboard contents, tokens, passwords or private
   messages.
6. **Explainability.** When you use a recipe, you may say »to sem že delala
   tako«. Do not expose raw internal scores.

## Storage

- Database: `~/.local/state/mia/learning.db` (SQLite, WAL).
- Control audit: `~/.local/state/mia/control-audit.jsonl`.
- Config: `learning:` block in `server/config/server.yaml`, or
  `MIA_LEARNING_DB` / `MIA_LEARNING_ENABLED`.
- HUD: **ZNANJE** page (`/hud/learning.html`) shows the tree, habits, recipes,
  mistakes and search.

## References

- `references/learning-protocol.md` — schemas, examples, promotion rules.
