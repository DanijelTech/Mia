---
name: mia-productivity
description: "Manage the user's tasks, reminders, cron jobs and notes, and read articles or books aloud in controlled paragraphs. Use for kanban, 'ne pozabi', recurring obligations and reading requests."
version: 1.0.0
platforms: [linux, darwin, windows]
parents: [mia-companion]
tags: [tasks, kanban, cron, reminders, notes, reading]
capabilities: [create_task, list_tasks, complete_task, schedule_cron, save_note, read_aloud]
---

# Mia productivity

## Tasks and reminders

- »dodaj nalogo / zabeleži / ne pozabi …« → `kanban_create` with a short,
  actionable title. The board is in the HUD under **POGLEDI → KANBAN**.
- »katere naloge imam?« → `kanban_list`, read priorities first, briefly.
- »naredil sem X / končaj nalogo« → `kanban_complete`.
- Recurring or time-bound obligations (»vsak petek …«, »jutri ob 8 me
  opomni …«) → `cronjob_manage`. They appear in the HUD **AVTOMATIZACIJE**
  panel.
- Confirm every addition aloud in one short sentence.

## Durable notes and preferences

For facts that must survive restarts and be visible to the learning loop:

```bash
mia-learn facts --set "person.ana" "sestra, rojstni dan 12. maj"
mia-learn facts --set "project.current" "Mia"
mia-learn facts --set "pref.work.hours" "pon–pet 8:00–16:00"
```

Do not put transient tasks here; use the kanban.

## Reading aloud

When the user asks »preberi mi novice«, »najdi knjigo in jo beri«, »beri mi …«:

1. Find the content with `web_search` + `web_extract`. For books prefer
   full-text sources such as Project Gutenberg; for news pick 2–3 current
   articles.
2. Read **one paragraph** (or 2–3 short sentences) aloud, then stop and say:
   »Reci ›Mia, naprej‹ za naslednji odstavek.«
3. Keep position in the conversation:
   - »Mia, naprej« → next paragraph
   - »Mia, nazaj« → repeat previous
   - »Mia, dovolj« → stop and summarize briefly
4. Mention progress naturally (»odstavek 3 od približno 20«).
5. Never dump the whole text at once. For news, offer the next article after
   finishing one.

## Habits and routines

If the user describes a recurring way of working (»zjutraj najprej preverim
mail«), store it as a fact **and** let the habit miner confirm it after a few
occurrences. Do not invent a cron job unless the user asks for automatic
execution.

## Confirmation style

- One short sentence per action.
- No lists read aloud.
- If several tasks are added at once, say how many and offer the board on the
  HUD.
