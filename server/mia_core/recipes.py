"""Procedural memory: recipes that worked, anti-patterns that did not.

Matching is intentionally lexical (token overlap + sequence ratio) rather than
embedding-based: it must run offline, deterministically and instantly on a
small CPU, and it must be explainable to the user ("uporabila sem recept ...").
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .db import Store

_STOP = {
    # Slovenian
    "mi", "me", "se", "si", "smo", "ste", "je", "so", "bi", "bo", "da", "ne",
    "in", "ter", "pa", "na", "za", "od", "do", "z", "s", "k", "h", "v",
    "prosim", "hvala", "zdaj", "sedaj", "potem", "prej", "lahko", "ali", "ki",
    "to", "ta", "te", "ti", "tisti", "tista", "moj", "moja", "moje", "tvoj",
    "tvoja", "tvoje", "mia", "mijo", "mija", "mio", "sefe", "šefe", "gospa",
    "gospod", "daj", "no", "ja", "ok", "okej", "kar", "kot", "tako", "zelo",
    # Serbian/Croatian
    "molim", "sam", "nije", "nema", "ajde", "hajde",
    "molimte", "brate", "gde", "gdje", "šta", "sta", "kako", "koji",
    # English
    "the", "a", "an", "please", "can", "you", "could", "would", "for",
    "of", "and", "or", "is", "are", "it", "this", "that", "my", "i",
    "want", "need",
}

_PUNCT = re.compile(r"[^a-z0-9čćžšđ]+")


def normalize(text: str) -> list[str]:
    """Lowercase, strip diacritics and punctuation, drop filler words."""
    if not text:
        return []
    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d")
    text = _PUNCT.sub(" ", text)
    return [t for t in text.split() if t and t not in _STOP]


def recipe_key(text: str) -> str:
    tokens = sorted(set(normalize(text)))
    return "-".join(tokens)[:180] or "unknown"


def _tokens(text: str) -> set[str]:
    return set(normalize(text))


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    jaccard = inter / len(ta | tb)
    containment = inter / min(len(ta), len(tb))
    seq = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return round(0.50 * jaccard + 0.30 * containment + 0.20 * seq, 4)


def match_recipes(store: Store, request: str, limit: int = 3,
                  threshold: float = 0.52) -> list[dict]:
    scored: list[tuple[float, dict]] = []
    key = recipe_key(request)
    for recipe in store.list_recipes(limit=200):
        if recipe["key"] == key:
            score = 1.0
        else:
            hay = " ".join(filter(None, [recipe.get("title"), recipe.get("intent"),
                                         " ".join(recipe.get("tags") or [])]))
            score = similarity(request, hay)
        if score >= threshold:
            scored.append((score, recipe))
    scored.sort(key=lambda item: (item[0], item[1].get("confidence") or 0), reverse=True)
    out = []
    for score, recipe in scored[: max(1, limit)]:
        item = dict(recipe)
        item["score"] = score
        out.append(item)
    return out


def match_anti_patterns(store: Store, request: str, limit: int = 3,
                        threshold: float = 0.40) -> list[dict]:
    scored: list[tuple[float, dict]] = []
    for ap in store.list_anti_patterns(limit=200):
        hay = " ".join(filter(None, [ap.get("symptom"), ap.get("cause"), ap.get("fix"),
                                     " ".join(ap.get("tags") or [])]))
        score = similarity(request, hay)
        if score >= threshold:
            scored.append((score, ap))
    scored.sort(key=lambda item: (item[0], item[1].get("hits") or 0), reverse=True)
    out = []
    for score, ap in scored[: max(1, limit)]:
        item = dict(ap)
        item["score"] = score
        out.append(item)
    return out


def _steps_text(steps: Any) -> str:
    if not steps:
        return ""
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
    return "; ".join(p for p in parts if p)[:1200]


def learn_from_episode(store: Store, episode: dict, cfg: dict | None = None) -> dict:
    """Turn one finished episode into durable procedural knowledge.

    Only episodes that actually did something (tools/steps) or that the user
    explicitly asked to remember become recipes — otherwise every trivial chat
    turn would flood the recipe book.
    """
    cfg = cfg or {}
    if not episode:
        return {"learned": False}
    steps = episode.get("steps") or []
    tools = episode.get("tools") or []
    meta = episode.get("meta") or {}
    request = episode.get("request") or episode.get("intent") or ""
    outcome = (episode.get("outcome") or "unknown").lower()
    verification_status = (episode.get("verification_status") or "").lower()
    if verification_status == "failed" and outcome == "success":
        outcome = "failure"
        episode["outcome"] = "failure"
        episode["error"] = (episode.get("error")
                            or "post-condition verification failed")
    should_learn = bool(steps or tools or meta.get("remember"))
    verified = (bool(episode.get("verified"))
                or (episode.get("verification_status") or "") in ("verified", "user_confirmed")
                or bool(meta.get("user_confirmed")))
    result: dict[str, Any] = {"learned": False}
    if outcome == "success" and should_learn and not verified:
        result = {"learned": False, "reason": "unverified",
                  "candidate": True,
                  "message": "procedure is stored but not trusted until verified or confirmed"}
    elif outcome == "success" and should_learn:
        key = recipe_key(request)
        rec_id = store.upsert_recipe(
            key=key,
            title=request[:200],
            intent=episode.get("intent") or "",
            steps=steps,
            tags=(episode.get("tags") or []) + [t for t in tools if isinstance(t, str)],
            notes=meta.get("recipe_note") or "",
            source=episode.get("source") or "learned",
            success=1,
        )
        result = {"learned": True, "kind": "recipe", "id": rec_id, "key": key}
        # a later success is evidence that the anti-pattern's fix works
        ap_key = _anti_key(request, episode.get("error") or "")
        if episode.get("error") and store.get_anti_pattern_by_key(ap_key):
            store.upsert_anti_pattern(
                key=ap_key, symptom=request, cause=episode.get("error") or "",
                fix=_steps_text(steps) or meta.get("recipe_note") or "",
                tags=episode.get("tags") or [], severity="medium", hits=0,
                bump_hits=False)
    elif outcome == "failure":
        error = episode.get("error") or meta.get("error") or "neznana napaka"
        key = _anti_key(request, error)
        store.upsert_anti_pattern(
            key=key, symptom=request, cause=error,
            fix=meta.get("recipe_note") or "",
            tags=(episode.get("tags") or []) + ["auto"],
            severity=meta.get("severity") or "medium",
        )
        rec_key = recipe_key(request)
        if store.get_recipe_by_key(rec_key):
            store.upsert_recipe(key=rec_key, title=request, fail=1)
        result = {"learned": True, "kind": "mistake", "key": key}
    return result


def _anti_key(request: str, error: str) -> str:
    digest = hashlib.sha1((error or "").encode("utf-8", "ignore")).hexdigest()[:10]
    return f"ap:{recipe_key(request)}:{digest}"


def record_feedback(store: Store, episode_id: int, verdict: str,
                    note: str = "", cfg: dict | None = None) -> dict:
    """Apply explicit user feedback ("to je bilo prav" / "ni prav")."""
    cfg = cfg or {}
    episode = store.get_episode(episode_id)
    if not episode:
        return {"ok": False, "error": f"episode {episode_id} not found"}
    verdict = (verdict or "").lower()
    positive = verdict in ("ok", "good", "correct", "right", "success",
                           "prav", "da", "positive", "yes", "true")
    store.record_feedback(episode_id, "positive" if positive else "negative", note)
    request = episode.get("request") or episode.get("intent") or ""
    rec_key = recipe_key(request)
    if positive:
        store.update_episode(episode_id, outcome="success", verified=1,
                             verification_status="user_confirmed",
                             verification={"status": "user_confirmed",
                                           "method": "user_feedback",
                                           "note": note})
        episode["outcome"] = "success"
        episode["verified"] = True
        episode["verification_status"] = "user_confirmed"
        if note:
            store.update_episode(episode_id, meta={**(episode.get("meta") or {}),
                                                   "recipe_note": note, "remember": True})
            episode["meta"] = {**(episode.get("meta") or {}), "recipe_note": note,
                               "remember": True}
        learned = learn_from_episode(store, episode, cfg)
        store.add_event("feedback_positive", str(episode_id), {"note": note})
        return {"ok": True, "verdict": "positive", "learned": learned,
                "recipe_key": rec_key}
    store.update_episode(episode_id, outcome="failure", verified=0,
                         verification_status="user_rejected",
                         verification={"status": "user_rejected",
                                       "method": "user_feedback",
                                       "note": note},
                         error=note or episode.get("error") or "user correction")
    episode["outcome"] = "failure"
    episode["error"] = note or episode.get("error") or "user correction"
    episode["verified"] = False
    episode["verification_status"] = "user_rejected"
    if note:
        episode["meta"] = {**(episode.get("meta") or {}), "recipe_note": note}
    learned = learn_from_episode(store, episode, cfg)
    store.add_event("feedback_negative", str(episode_id), {"note": note})
    return {"ok": True, "verdict": "negative", "learned": learned,
            "recipe_key": rec_key}


def remember_as_recipe(store: Store, episode_id: int, note: str = "") -> dict:
    episode = store.get_episode(episode_id)
    if not episode:
        return {"ok": False, "error": f"episode {episode_id} not found"}
    if not (episode.get("steps") or episode.get("tools")):
        return {"ok": False,
                "error": "previous episode has no steps/tools to save as a recipe"}
    meta = dict(episode.get("meta") or {})
    meta["remember"] = True
    if note:
        meta["recipe_note"] = note
    store.update_episode(episode_id, meta=meta, verified=1,
                         verification_status="user_confirmed",
                         verification={"status": "user_confirmed",
                                       "method": "remember_command",
                                       "note": note})
    episode["meta"] = meta
    episode["verified"] = True
    episode["verification_status"] = "user_confirmed"
    if (episode.get("outcome") or "") not in ("success", "failure"):
        episode["outcome"] = "success"
        store.update_episode(episode_id, outcome="success")
    return {"ok": True, **learn_from_episode(store, episode)}
