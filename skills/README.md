# Mia skill tree

Mia's knowledge is split into small, named skills instead of one giant prompt.
The agent reads the root skill first, then loads the child that owns the task.
The same tree is visible in the HUD (**ZNANJE → DREVO VEŠČIN**) and from the
command line:

```bash
mia-skill tree          # nested tree
mia-skill list          # flat list with descriptions
mia-skill validate      # fail on missing references / broken parents
mia-skill search "okno" # find the skill that owns a capability
```

## Structure

```
mia-companion        persona, language, routing, memory duty, safety
├── mia-desktop      windows, apps, input, screenshots, clipboard, power
├── mia-learning     episodes, habits, recipes, mistakes, feedback loop
├── mia-music        YouTube playback, history, favourite artists
├── mia-browser      web search, HUD panels, interactive browsing
├── mia-productivity kanban, cron, notes, reading aloud
└── mia-diagnostics  health, logs, restart, capability checks
```

## Rules

1. **One owner per capability.** If two skills describe the same action, the
   child wins and the root links to it.
2. **Descriptions are selection hints.** The description is what the model
   uses to decide whether to open the skill; keep it concrete.
3. **References hold the detail.** `SKILL.md` stays under ~450 lines; long
   command tables and examples live in `references/`.
4. **Everything is validated.** `mia-skill validate` checks front matter,
   duplicate names, missing parents and broken `references/` links.
5. **Installed, not copied by hand.** `install.sh` copies the whole tree into
   the active Hermes home (`$HERMES_HOME/skills`).

## Adding a skill

```bash
mkdir -p skills/mia-newname/references
$EDITOR skills/mia-newname/SKILL.md
# add "mia-newname" to skills/tree.yaml and to the parent's children list
mia-skill validate
./install.sh --yes            # or: mia-skill install "$HERMES_HOME"
```

Front matter example:

```yaml
---
name: mia-newname
description: "One sentence that tells the agent exactly when to use this."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [example]
capabilities: [do_one_thing, do_another]
---
```
