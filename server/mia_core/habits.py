"""Habit mining: turn raw episodes into explicit, reviewable routines.

Everything here is explainable: each habit carries the evidence count, the
observed time-of-day peak and a few examples. The agent gets a short version in
its per-turn context brief; the HUD shows the full version.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from typing import Any

from .db import Store
from .recipes import normalize

_PERIODS = (
    (5, 11, "zjutraj"),
    (11, 15, "opoldne"),
    (15, 19, "popoldne"),
    (19, 23, "zvečer"),
    (23, 5, "ponoči"),
)


def _period(hour: int) -> str:
    for start, end, label in _PERIODS:
        if start <= end and start <= hour < end:
            return label
        if start > end and (hour >= start or hour < end):
            return label
    return "podnevi"


def _confidence(count: int, last_seen: float, now: float) -> float:
    base = 1.0 - math.exp(-max(0, count) / 5.0)
    conf = 0.30 + 0.65 * base
    age_days = max(0.0, (now - last_seen) / 86400.0)
    if age_days > 14:
        conf *= math.exp(-(age_days - 14) / 90.0)
    return round(max(0.0, min(0.95, conf)), 4)


def _entities(episode: dict) -> list[tuple[str, str]]:
    """Extract (kind, value) pairs from structured metadata and tags."""
    out: list[tuple[str, str]] = []
    meta = episode.get("meta") or {}
    raw = meta.get("entities")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("value"):
                out.append((str(item.get("kind") or "entity"), str(item["value"])))
            elif isinstance(item, str):
                out.append(("entity", item))
    for key in ("app", "application", "url", "domain", "artist", "song", "query",
                "path", "project", "window", "service", "device"):
        value = meta.get(key)
        if value:
            out.append((key, str(value)))
    # control-audit episodes carry the URL in `request`, not in meta.entities
    for match in re.finditer(r"https?://([^/\s]+)", episode.get("request") or ""):
        out.append(("domain", match.group(1).lower()))
    for tag in episode.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("entity:"):
            kind, _, value = tag.partition(":")
            if value:
                out.append((kind or "entity", value))
    cleaned = []
    seen = set()
    for kind, value in out:
        value = " ".join(str(value).split())[:120]
        if not value:
            continue
        key = (kind.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        cleaned.append((kind.lower(), value))
    return cleaned


def _intent(episode: dict) -> str:
    intent = (episode.get("intent") or "").strip()
    if intent:
        return intent
    tokens = normalize(episode.get("request") or "")
    return " ".join(tokens[:4])


def mine_habits(store: Store, cfg: dict | None = None, apply: bool = True) -> dict:
    """Infer preferences and routines from recent episodes.

    Returns a summary dict with the candidates found. When `apply` is true the
    habits table is updated (new/updated habits, stale ones decayed).
    """
    cfg = cfg or {}
    hcfg = cfg.get("habits") or {}
    recency_days = int(hcfg.get("recency_days", 120))
    min_evidence = int(hcfg.get("min_evidence", 3))
    peak_share = float(hcfg.get("peak_share", 0.35))
    window_min = int(hcfg.get("sequence_window_minutes", 20))
    decay_after = int(hcfg.get("decay_after_days", 45))
    min_conf = float((cfg.get("retention") or {}).get("min_confidence", 0.12))
    now = time.time()
    since = now - recency_days * 86400
    episodes = store.list_episodes(limit=5000, since=since)
    episodes.sort(key=lambda e: e.get("ts") or 0)

    candidates: list[dict] = []
    entity_times: dict[tuple[str, str], list[float]] = defaultdict(list)
    entity_examples: dict[tuple[str, str], list[str]] = defaultdict(list)

    for ep in episodes:
        if (ep.get("outcome") or "unknown") in ("failure",):
            continue
        for kind, value in _entities(ep):
            entity_times[(kind, value)].append(float(ep.get("ts") or now))
            if len(entity_examples[(kind, value)]) < 3:
                entity_examples[(kind, value)].append((ep.get("request") or "")[:120])

    for (kind, value), times in entity_times.items():
        count = len(times)
        if count < min_evidence:
            continue
        last_seen = max(times)
        hist = Counter(time.localtime(t).tm_hour for t in times)
        peak_hour, peak_count = _peak_window(hist)
        share = peak_count / count
        detail: dict[str, Any] = {
            "count": count,
            "last_seen": last_seen,
            "examples": entity_examples[(kind, value)],
            "period": _period(peak_hour),
            "peak_hour": peak_hour,
            "peak_share": round(share, 2),
            "first_seen": min(times),
        }
        if share >= peak_share and count >= min_evidence:
            detail["routine"] = f"običajno {_period(peak_hour)} (~{peak_hour:02d}:00)"
        candidates.append({
            "kind": "preference",
            "subject": f"{kind}: {value}",
            "key": f"habit:pref:{kind}:{' '.join(normalize(value))[:80]}",
            "detail": detail,
            "evidence": count,
            "confidence": _confidence(count, last_seen, now),
        })

    # Repeated adjacent actions: "odpri glasbo -> nastavi glasnost"
    pair_counts: Counter[tuple[str, str]] = Counter()
    pair_last: dict[tuple[str, str], float] = {}
    pair_examples: dict[tuple[str, str], list[str]] = defaultdict(list)
    prev: dict | None = None
    for ep in episodes:
        cur_intent = _intent(ep)
        ts = float(ep.get("ts") or 0)
        if prev and cur_intent:
            prev_intent = _intent(prev)
            prev_ts = float(prev.get("ts") or 0)
            if prev_intent and 0 <= ts - prev_ts <= window_min * 60:
                pair = (prev_intent, cur_intent)
                pair_counts[pair] += 1
                pair_last[pair] = max(pair_last.get(pair, 0), ts)
                if len(pair_examples[pair]) < 3:
                    pair_examples[pair].append(
                        f"{prev.get('request', '')[:60]} → {ep.get('request', '')[:60]}")
        prev = ep
    for pair, count in pair_counts.items():
        if count < min_evidence:
            continue
        last_seen = pair_last.get(pair, now)
        candidates.append({
            "kind": "routine",
            "subject": f"{pair[0]} → {pair[1]}",
            "key": f"habit:seq:{pair[0]}->{pair[1]}"[:160],
            "detail": {"count": count, "last_seen": last_seen,
                       "examples": pair_examples[pair],
                       "window_minutes": window_min},
            "evidence": count,
            "confidence": _confidence(count, last_seen, now),
        })

    # Explicit preference facts (volume, language, browser, ...)
    facts = store.list_facts(limit=200)
    for fact in facts:
        if fact.get("kind") in ("preference", "habit"):
            candidates.append({
                "kind": "fact",
                "subject": f"{fact['key']}: {fact.get('value')}",
                "key": f"habit:fact:{fact['key']}"[:160],
                "detail": {"value": fact.get("value"), "source": fact.get("source"),
                           "updated": fact.get("updated")},
                "evidence": 3,
                "confidence": float(fact.get("confidence") or 0.7),
            })

    applied = 0
    if apply:
        for cand in candidates:
            store.upsert_habit(
                key=cand["key"], kind=cand["kind"], subject=cand["subject"],
                detail=cand["detail"], evidence=cand["evidence"],
                confidence=cand["confidence"],
            )
            applied += 1
        # decay habits that stopped appearing
        stale_cut = now - decay_after * 86400
        rows = store.list_habits(limit=1000, min_confidence=0.0)
        for habit in rows:
            if habit.get("pinned"):
                continue
            if float(habit.get("last_seen") or 0) < stale_cut:
                new_conf = round(float(habit.get("confidence") or 0) * 0.85, 4)
                if new_conf < min_conf:
                    store.delete_habit(habit["key"])
                else:
                    store._execute("UPDATE habits SET confidence=? WHERE key=?",
                                   (new_conf, habit["key"]))
        store.add_event("habit_mine", "", {"candidates": len(candidates),
                                           "applied": applied,
                                           "episodes": len(episodes)})
    return {
        "episodes_considered": len(episodes),
        "candidates": candidates,
        "applied": applied,
    }


def _peak_window(hist: Counter) -> tuple[int, int]:
    """Best 2-hour window (handles the 23->0 wrap)."""
    best_hour, best_sum = 0, -1
    for hour in range(24):
        total = hist.get(hour, 0) + hist.get((hour + 1) % 24, 0)
        if total > best_sum:
            best_hour, best_sum = hour, total
    return best_hour, max(0, best_sum)


def top_habits(store: Store, limit: int = 10, min_confidence: float = 0.35) -> list[dict]:
    return store.list_habits(limit=limit, min_confidence=min_confidence)


def habit_lines(habits: list[dict], limit: int = 6) -> list[str]:
    lines = []
    for habit in habits[:limit]:
        detail = habit.get("detail") or {}
        subject = habit.get("subject") or ""
        if habit.get("kind") == "routine":
            lines.append(f"navada: {subject} ({detail.get('count', '?')}×)")
        elif detail.get("routine"):
            lines.append(f"{subject} — {detail['routine']} ({detail.get('count', '?')}×)")
        else:
            lines.append(f"{subject} ({detail.get('count', '?')}×)")
    return lines
