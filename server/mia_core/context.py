"""Build the compact memory brief that is injected into every agent turn.

The brief is deterministic, bounded and honest: it only contains things that
were actually observed or explicitly confirmed. It is the difference between
"the agent has a memory somewhere" and "the agent uses it before acting".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import Store
from .habits import habit_lines
from .recipes import match_anti_patterns, match_recipes

HEADER = "[MIA SPOMIN — uporabi to pred dejanjem, ne sprašuj znova]"
FOOTER = ("[konec spomina] Po opravilu se izid zabeleži sam; če uporabnik reče "
          "»to je bilo prav« ali »ni prav«, se recept/napaka posodobi.")


def _recipe_steps(recipe: dict, max_chars: int = 260) -> str:
    steps = recipe.get("steps") or []
    parts = []
    for step in steps:
        if isinstance(step, dict):
            label = step.get("action") or step.get("tool") or step.get("cmd") or ""
            detail = step.get("args") or step.get("preview") or step.get("out") or ""
            if isinstance(detail, (list, tuple)):
                detail = " ".join(map(str, detail))
            parts.append(f"{label} {detail}".strip())
        else:
            parts.append(str(step))
    text = " → ".join(p for p in parts if p)
    return text[:max_chars]


def build_brief(store: Store, cfg: dict, request: str = "",
                skills_root: str | Path | None = None) -> str:
    ccfg = cfg.get("context") or {}
    if not ccfg.get("enabled", True):
        return ""
    max_chars = int(ccfg.get("max_chars", 1500))
    sections: list[tuple[int, list[str]]] = []  # (priority, lines)

    habits = store.list_habits(limit=40, min_confidence=0.30)
    if request:
        from .recipes import similarity
        scored = [(similarity(request, f"{h.get('subject', '')} {h.get('detail', {})}"), h)
                  for h in habits]
        scored = [x for x in scored if x[0] >= 0.10]
        scored.sort(key=lambda x: (x[0], x[1].get("confidence") or 0), reverse=True)
        relevant = [h for _, h in scored[: int(ccfg.get("max_habits", 6))]]
        if not relevant:
            relevant = habits[: int(ccfg.get("max_habits", 6))]
    else:
        relevant = habits[: int(ccfg.get("max_habits", 6))]
    habit_text = habit_lines(relevant, int(ccfg.get("max_habits", 6)))
    if habit_text:
        sections.append((10, ["Navade uporabnika:"] + [f"- {line}" for line in habit_text]))

    recipes = match_recipes(store, request, limit=int(ccfg.get("max_recipes", 2)),
                            threshold=float((cfg.get("recipes") or {}).get("match_threshold", 0.52))) if request else []
    if recipes:
        lines = ["Preverjeni postopki za to zahtevo:"]
        for recipe in recipes:
            steps = _recipe_steps(recipe)
            lines.append(
                f"- {recipe.get('title') or recipe.get('key')} "
                f"(zaupanje {float(recipe.get('confidence') or 0):.2f}, "
                f"{recipe.get('success_count', 0)}× uspešno): {steps}")
        sections.append((30, lines))

    mistakes = match_anti_patterns(store, request, limit=int(ccfg.get("max_mistakes", 3))) if request else []
    if mistakes:
        lines = ["Tega NE ponavljaj:"]
        for ap in mistakes:
            cause = ap.get("cause") or ""
            fix = ap.get("fix") or ""
            lines.append(f"- {ap.get('symptom')} — vzrok: {cause}" +
                         (f"; rešitev: {fix}" if fix else ""))
        sections.append((40, lines))

    facts = store.list_facts(limit=40)
    preferred = [f for f in facts if f.get("kind") in ("preference", "habit", "system")]
    if preferred:
        lines = ["Znane nastavitve in dejstva:"]
        for fact in preferred[: int(ccfg.get("max_facts", 5))]:
            lines.append(f"- {fact['key']}: {fact.get('value')}")
        sections.append((20, lines))

    if ccfg.get("include_skills", True) and skills_root:
        try:
            from .knowledge import skill_context_lines
            skill_lines = skill_context_lines(skills_root, request, limit=6)
            if skill_lines:
                sections.append((50, ["Razpoložljive veščine (podrobnosti v SKILL.md):"] +
                                 [f"- {line}" for line in skill_lines]))
        except Exception:
            pass

    # assemble by priority, then drop the least important section until it fits
    sections.sort(key=lambda x: x[0])
    while sections:
        lines = [HEADER]
        for _, section in sections:
            lines.extend(section)
        lines.append(FOOTER)
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        sections.pop()
    return ""


def brief_preview(store: Store, cfg: dict, request: str = "",
                  skills_root: str | Path | None = None) -> dict:
    text = build_brief(store, cfg, request, skills_root)
    return {"chars": len(text), "text": text,
            "max_chars": int((cfg.get("context") or {}).get("max_chars", 1500))}
