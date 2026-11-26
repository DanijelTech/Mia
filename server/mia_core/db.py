"""SQLite persistence for Mia's durable memory.

Design notes
------------
* WAL + busy_timeout: the voice server, the HUD and CLIs may write at once.
* One connection guarded by an RLock: simpler and safer than per-thread pools
  for this workload, and SQLite serialises writes anyway.
* Every text field is redacted and clipped before it is stored.
* FTS5 is used when the local SQLite has it; LIKE is the always-works fallback.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from . import privacy

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    session TEXT,
    source TEXT NOT NULL DEFAULT 'unknown',
    intent TEXT,
    request TEXT,
    response TEXT,
    tools TEXT,
    steps TEXT,
    outcome TEXT,
    error TEXT,
    duration_s REAL,
    interrupted INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0,
    verification_status TEXT DEFAULT 'unverified',
    verification TEXT,
    tags TEXT,
    meta TEXT,
    fingerprint TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session, ts DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_source ON episodes(source, ts DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_outcome ON episodes(outcome);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER,
    ts REAL NOT NULL,
    verdict TEXT NOT NULL,
    note TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedback_episode ON feedback(episode_id, ts DESC);
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    title TEXT,
    intent TEXT,
    steps TEXT,
    tags TEXT,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    last_used REAL,
    created REAL NOT NULL,
    updated REAL NOT NULL,
    notes TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_recipes_conf ON recipes(confidence DESC, last_used DESC);
CREATE TABLE IF NOT EXISTS anti_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    symptom TEXT,
    cause TEXT,
    fix TEXT,
    tags TEXT,
    severity TEXT DEFAULT 'medium',
    hits INTEGER DEFAULT 1,
    last_seen REAL,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anti_hits ON anti_patterns(hits DESC, last_seen DESC);
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    detail TEXT,
    evidence INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.0,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    pinned INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_habits_conf ON habits(confidence DESC, evidence DESC);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    kind TEXT,
    tags TEXT,
    confidence REAL DEFAULT 0.7,
    source TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_nodes (
    path TEXT PRIMARY KEY,
    name TEXT,
    title TEXT,
    description TEXT,
    parent TEXT,
    tags TEXT,
    capabilities TEXT,
    mtime REAL,
    size INTEGER,
    hash TEXT,
    health TEXT,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY,
    category TEXT,
    label TEXT,
    how TEXT,
    keywords TEXT,
    status TEXT DEFAULT 'empty',
    evidence TEXT,
    notes TEXT,
    last_checked REAL,
    last_confirmed REAL,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_capabilities_cat ON capabilities(category, status);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
CREATE TABLE IF NOT EXISTS audit_ingest (
    path TEXT PRIMARY KEY,
    offset INTEGER NOT NULL DEFAULT 0,
    updated REAL NOT NULL
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    kind, ref UNINDEXED, text, tokenize='unicode61'
);
"""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class Store:
    """Thread-safe SQLite store. All public methods are safe to call anywhere."""

    def __init__(self, path: str | Path, timeout: float = 15.0,
                 privacy_cfg: dict | None = None):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.privacy_cfg = privacy_cfg or {}
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), timeout=timeout,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._fts = False
        self._closed = False
        self._configure()
        self._migrate()

    # ------------------------------------------------------------- plumbing
    def _configure(self) -> None:
        with self._lock:
            for pragma in (
                "PRAGMA journal_mode=WAL",
                "PRAGMA synchronous=NORMAL",
                "PRAGMA foreign_keys=ON",
                "PRAGMA busy_timeout=8000",
                "PRAGMA temp_store=MEMORY",
            ):
                try:
                    self._conn.execute(pragma)
                except sqlite3.Error:
                    pass

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            try:
                self._conn.executescript(_FTS_SCHEMA)
                self._fts = True
            except sqlite3.Error:
                self._fts = False
            # Forward migration for databases created before verified learning.
            columns = {row["name"] for row in self._conn.execute(
                "PRAGMA table_info(episodes)").fetchall()}
            for name, ddl in (
                ("verified", "ALTER TABLE episodes ADD COLUMN verified INTEGER DEFAULT 0"),
                ("verification_status",
                 "ALTER TABLE episodes ADD COLUMN verification_status TEXT DEFAULT 'unverified'"),
                ("verification", "ALTER TABLE episodes ADD COLUMN verification TEXT"),
            ):
                if name not in columns:
                    try:
                        self._conn.execute(ddl)
                    except sqlite3.Error:
                        pass
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                try:
                    self._conn.commit()
                finally:
                    self._conn.close()
                self._closed = True

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    def _one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    # --------------------------------------------------------------- meta
    def meta_get(self, key: str, default: str | None = None) -> str | None:
        row = self._one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else default

    def meta_set(self, key: str, value: Any) -> None:
        self._execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    # ------------------------------------------------------------- privacy
    def _safe(self, text: Any, limit: int | None = None) -> str:
        raw = "" if text is None else str(text)
        if self.privacy_cfg.get("redact", True):
            raw = privacy.redact(raw, limit)
        elif limit is not None:
            raw = privacy.clip(raw, limit)
        return raw

    # ------------------------------------------------------------ episodes
    def record_episode(self, **fields: Any) -> int:
        now = float(fields.pop("ts", time.time()) or time.time())
        pcfg = self.privacy_cfg
        request = self._safe(fields.get("request"), int(pcfg.get("max_text_chars", 4000)))
        response = self._safe(fields.get("response"), int(pcfg.get("max_response_chars", 2000)))
        error = self._safe(fields.get("error"), 1000)
        steps = fields.get("steps") or []
        tools = fields.get("tools") or []
        tags = fields.get("tags") or []
        meta = fields.get("meta") or {}
        if pcfg.get("redact", True):
            steps = privacy.redact_obj(steps, 500)
            meta = privacy.redact_obj(meta, 500)
        verification = fields.get("verification") or {}
        verified = bool(fields.get("verified")) or verification.get("status") == "verified"
        verification_status = (fields.get("verification_status")
                               or verification.get("status")
                               or ("verified" if verified else "unverified"))
        cur = self._execute(
            """INSERT INTO episodes
               (ts, session, source, intent, request, response, tools, steps,
                outcome, error, duration_s, interrupted, verified,
                verification_status, verification, tags, meta, fingerprint)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now, fields.get("session"), fields.get("source") or "unknown",
                self._safe(fields.get("intent"), 300), request, response,
                _dumps(tools), _dumps(steps), fields.get("outcome") or "unknown",
                error, fields.get("duration_s"), 1 if fields.get("interrupted") else 0,
                1 if verified else 0, verification_status,
                _dumps(privacy.redact_obj(verification, 500)
                       if self.privacy_cfg.get("redact", True) else verification),
                _dumps(tags), _dumps(meta), fields.get("fingerprint"),
            ),
        )
        ep_id = int(cur.lastrowid)
        self._index("episode", ep_id, " ".join(filter(None, [
            request, response, " ".join(str(t) for t in tags),
            self._safe(fields.get("intent"), 300),
        ])))
        return ep_id

    def update_episode(self, episode_id: int, **fields: Any) -> bool:
        allowed = {"outcome", "error", "response", "interrupted", "duration_s",
                   "steps", "tools", "tags", "meta", "intent", "verified",
                   "verification_status", "verification"}
        sets, params = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in ("steps", "tools", "tags", "meta", "verification"):
                value = _dumps(privacy.redact_obj(value, 500)
                               if self.privacy_cfg.get("redact", True) else value)
            elif key == "verified":
                value = 1 if value else 0
            elif key == "error":
                value = self._safe(value, 1000)
            elif key == "response":
                value = self._safe(value, int(self.privacy_cfg.get("max_response_chars", 2000)))
            sets.append(f"{key}=?")
            params.append(value)
        if not sets:
            return False
        params.append(episode_id)
        self._execute(f"UPDATE episodes SET {', '.join(sets)} WHERE id=?", params)
        row = self.get_episode(episode_id)
        if row:
            self._index("episode", episode_id, " ".join(filter(None, [
                row.get("request"), row.get("response"), row.get("intent")])))
        return True

    def get_episode(self, episode_id: int) -> dict | None:
        row = self._one("SELECT * FROM episodes WHERE id=?", (episode_id,))
        return self._episode_dict(row) if row else None

    def last_episode(self, session: str | None = None,
                     source: str | None = None) -> dict | None:
        sql = "SELECT * FROM episodes WHERE 1=1"
        params: list[Any] = []
        if session:
            sql += " AND session=?"
            params.append(session)
        if source:
            sql += " AND source=?"
            params.append(source)
        sql += " ORDER BY id DESC LIMIT 1"
        row = self._one(sql, params)
        return self._episode_dict(row) if row else None

    def list_episodes(self, limit: int = 50, offset: int = 0,
                      source: str | None = None, outcome: str | None = None,
                      session: str | None = None,
                      verification_status: str | None = None,
                      since: float | None = None) -> list[dict]:
        sql = "SELECT * FROM episodes WHERE 1=1"
        params: list[Any] = []
        for column, value in (("source", source), ("outcome", outcome),
                              ("session", session),
                              ("verification_status", verification_status)):
            if value:
                sql += f" AND {column}=?"
                params.append(value)
        if since:
            sql += " AND ts>=?"
            params.append(since)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        return [self._episode_dict(r) for r in self._query(sql, params)]

    @staticmethod
    def _episode_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        for key in ("tools", "steps", "tags", "meta"):
            d[key] = _loads(d.get(key), [] if key != "meta" else {})
        d["verification"] = _loads(d.get("verification"), {})
        d["interrupted"] = bool(d.get("interrupted"))
        d["verified"] = bool(d.get("verified"))
        d.setdefault("verification_status", "unverified")
        return d

    # ------------------------------------------------------------ feedback
    def record_feedback(self, episode_id: int | None, verdict: str,
                        note: str = "", source: str = "user") -> int:
        cur = self._execute(
            "INSERT INTO feedback(episode_id, ts, verdict, note, source) VALUES(?,?,?,?,?)",
            (episode_id, time.time(), verdict, self._safe(note, 800), source),
        )
        self.add_event("feedback", str(episode_id or ""), {"verdict": verdict, "note": note})
        return int(cur.lastrowid)

    def list_feedback(self, episode_id: int | None = None, limit: int = 50) -> list[dict]:
        if episode_id is None:
            rows = self._query("SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limit,))
        else:
            rows = self._query(
                "SELECT * FROM feedback WHERE episode_id=? ORDER BY id DESC LIMIT ?",
                (episode_id, limit))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- recipes
    def upsert_recipe(self, key: str, title: str = "", intent: str = "",
                      steps: Any = None, tags: Any = None, notes: str = "",
                      source: str = "learned", success: int = 0,
                      fail: int = 0, confidence: float | None = None) -> int:
        now = time.time()
        existing = self.get_recipe_by_key(key)
        if existing:
            new_success = int(existing["success_count"]) + success
            new_fail = int(existing["fail_count"]) + fail
            conf = confidence if confidence is not None else self._confidence(
                new_success, new_fail)
            # A feedback update passes only the counters. Never let it wipe the
            # procedure that made the recipe valuable in the first place.
            steps_value = (_dumps(existing["steps"] or []) if steps is None else
                           _dumps(privacy.redact_obj(steps, 500)
                                  if self.privacy_cfg.get("redact", True) else steps))
            tags_value = _dumps(existing["tags"] or []) if tags is None else _dumps(tags)
            self._execute(
                """UPDATE recipes SET title=?, intent=?, steps=?, tags=?, notes=?,
                   source=?, success_count=?, fail_count=?, confidence=?,
                   last_used=?, updated=? WHERE key=?""",
                (self._safe(title, 300) or existing["title"],
                 self._safe(intent, 300) or existing["intent"],
                 steps_value, tags_value,
                 self._safe(notes, 800) or existing["notes"],
                 source or existing["source"], new_success, new_fail, conf,
                 now, now, key),
            )
            rec_id = int(existing["id"])
        else:
            conf = confidence if confidence is not None else self._confidence(success, fail)
            cur = self._execute(
                """INSERT INTO recipes(key, title, intent, steps, tags, success_count,
                   fail_count, confidence, last_used, created, updated, notes, source)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, self._safe(title, 300), self._safe(intent, 300),
                 _dumps(privacy.redact_obj(steps, 500) if self.privacy_cfg.get("redact", True) else steps),
                 _dumps(tags or []), success, fail, conf, now, now, now,
                 self._safe(notes, 800), source),
            )
            rec_id = int(cur.lastrowid)
        self._index("recipe", rec_id, " ".join(filter(None, [
            title, intent, notes, " ".join(map(str, tags or []))])))
        return rec_id

    @staticmethod
    def _confidence(success: int, fail: int, saturation: float = 3.0) -> float:
        n = max(1, success + fail)
        rate = (success + 1.0) / (success + fail + 2.0)
        sat = 1.0 - pow(2.718281828, -n / max(0.5, saturation))
        return round(max(0.0, min(0.99, rate * sat)), 4)

    def get_recipe_by_key(self, key: str) -> dict | None:
        row = self._one("SELECT * FROM recipes WHERE key=?", (key,))
        return self._recipe_dict(row) if row else None

    def get_recipe(self, recipe_id: int) -> dict | None:
        row = self._one("SELECT * FROM recipes WHERE id=?", (recipe_id,))
        return self._recipe_dict(row) if row else None

    @staticmethod
    def _recipe_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["steps"] = _loads(d.get("steps"), [])
        d["tags"] = _loads(d.get("tags"), [])
        return d

    def list_recipes(self, limit: int = 50, min_confidence: float = 0.0) -> list[dict]:
        rows = self._query(
            "SELECT * FROM recipes WHERE confidence>=? "
            "ORDER BY confidence DESC, success_count DESC, last_used DESC LIMIT ?",
            (min_confidence, max(1, int(limit))),
        )
        return [self._recipe_dict(r) for r in rows]

    def delete_recipe(self, key_or_id: str | int) -> bool:
        if isinstance(key_or_id, int) or str(key_or_id).isdigit():
            cur = self._execute("DELETE FROM recipes WHERE id=?", (int(key_or_id),))
        else:
            cur = self._execute("DELETE FROM recipes WHERE key=?", (str(key_or_id),))
        return cur.rowcount > 0

    # -------------------------------------------------------- anti-patterns
    def upsert_anti_pattern(self, key: str, symptom: str, cause: str = "",
                            fix: str = "", tags: Any = None,
                            severity: str = "medium", hits: int = 1) -> int:
        now = time.time()
        existing = self._one("SELECT * FROM anti_patterns WHERE key=?", (key,))
        if existing:
            self._execute(
                """UPDATE anti_patterns SET symptom=?, cause=?, fix=?, tags=?,
                   severity=?, hits=hits+?, last_seen=?, updated=? WHERE key=?""",
                (self._safe(symptom, 500) or existing["symptom"],
                 self._safe(cause, 500) or existing["cause"],
                 self._safe(fix, 500) or existing["fix"],
                 _dumps(tags or _loads(existing["tags"], [])),
                 severity or existing["severity"], max(1, hits), now, now, key),
            )
            ap_id = int(existing["id"])
        else:
            cur = self._execute(
                """INSERT INTO anti_patterns(key, symptom, cause, fix, tags, severity,
                   hits, last_seen, created, updated) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (key, self._safe(symptom, 500), self._safe(cause, 500),
                 self._safe(fix, 500), _dumps(tags or []), severity, max(1, hits),
                 now, now, now),
            )
            ap_id = int(cur.lastrowid)
        self._index("mistake", ap_id, " ".join(filter(None, [
            symptom, cause, fix, " ".join(map(str, tags or []))])))
        return ap_id

    def list_anti_patterns(self, limit: int = 50) -> list[dict]:
        rows = self._query(
            "SELECT * FROM anti_patterns ORDER BY hits DESC, last_seen DESC LIMIT ?",
            (max(1, int(limit)),))
        out = []
        for row in rows:
            d = dict(row)
            d["tags"] = _loads(d.get("tags"), [])
            out.append(d)
        return out

    def get_anti_pattern_by_key(self, key: str) -> dict | None:
        row = self._one("SELECT * FROM anti_patterns WHERE key=?", (key,))
        if not row:
            return None
        d = dict(row)
        d["tags"] = _loads(d.get("tags"), [])
        return d

    def delete_anti_pattern(self, key_or_id: str | int) -> bool:
        if isinstance(key_or_id, int) or str(key_or_id).isdigit():
            cur = self._execute("DELETE FROM anti_patterns WHERE id=?", (int(key_or_id),))
        else:
            cur = self._execute("DELETE FROM anti_patterns WHERE key=?", (str(key_or_id),))
        return cur.rowcount > 0

    # -------------------------------------------------------------- habits
    def upsert_habit(self, key: str, kind: str, subject: str, detail: Any = None,
                     evidence: int = 1, confidence: float = 0.5,
                     pinned: bool | None = None) -> int:
        now = time.time()
        existing = self._one("SELECT * FROM habits WHERE key=?", (key,))
        if existing:
            conf = max(float(existing["confidence"]) * 0.98, float(confidence))
            pinned_value = int(existing["pinned"]) if pinned is None else int(bool(pinned))
            self._execute(
                """UPDATE habits SET kind=?, subject=?, detail=?, evidence=?,
                   confidence=?, last_seen=?, pinned=? WHERE key=?""",
                (kind, self._safe(subject, 300),
                 _dumps(privacy.redact_obj(detail, 400) if self.privacy_cfg.get("redact", True) else detail),
                 max(int(existing["evidence"]), int(evidence)), conf, now,
                 pinned_value, key),
            )
            habit_id = int(existing["id"])
        else:
            cur = self._execute(
                """INSERT INTO habits(key, kind, subject, detail, evidence, confidence,
                   first_seen, last_seen, pinned) VALUES(?,?,?,?,?,?,?,?,?)""",
                (key, kind, self._safe(subject, 300),
                 _dumps(privacy.redact_obj(detail, 400) if self.privacy_cfg.get("redact", True) else detail),
                 max(1, int(evidence)), round(float(confidence), 4), now, now,
                 int(bool(pinned))),
            )
            habit_id = int(cur.lastrowid)
        self._index("habit", habit_id, f"{subject} {_dumps(detail)}")
        return habit_id

    def list_habits(self, limit: int = 50, min_confidence: float = 0.0) -> list[dict]:
        rows = self._query(
            "SELECT * FROM habits WHERE confidence>=? "
            "ORDER BY pinned DESC, confidence DESC, evidence DESC LIMIT ?",
            (min_confidence, max(1, int(limit))),
        )
        out = []
        for row in rows:
            d = dict(row)
            d["detail"] = _loads(d.get("detail"), {})
            d["pinned"] = bool(d.get("pinned"))
            out.append(d)
        return out

    def delete_habit(self, key: str) -> bool:
        return self._execute("DELETE FROM habits WHERE key=?", (key,)).rowcount > 0

    # --------------------------------------------------------------- facts
    def upsert_fact(self, key: str, value: str, kind: str = "preference",
                    tags: Any = None, confidence: float = 0.7,
                    source: str = "learned") -> int:
        now = time.time()
        self._execute(
            """INSERT INTO facts(key, value, kind, tags, confidence, source, created, updated)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, kind=excluded.kind,
                 tags=excluded.tags, confidence=excluded.confidence,
                 source=excluded.source, updated=excluded.updated""",
            (key, self._safe(value, 1000), kind, _dumps(tags or []),
             round(float(confidence), 4), source, now, now),
        )
        row = self._one("SELECT id FROM facts WHERE key=?", (key,))
        fid = int(row["id"]) if row else 0
        self._index("fact", fid, f"{key} {value} {' '.join(map(str, tags or []))}")
        return fid

    def get_fact(self, key: str) -> dict | None:
        row = self._one("SELECT * FROM facts WHERE key=?", (key,))
        if not row:
            return None
        d = dict(row)
        d["tags"] = _loads(d.get("tags"), [])
        return d

    def list_facts(self, limit: int = 100, kind: str | None = None) -> list[dict]:
        if kind:
            rows = self._query(
                "SELECT * FROM facts WHERE kind=? ORDER BY confidence DESC, updated DESC LIMIT ?",
                (kind, max(1, int(limit))))
        else:
            rows = self._query(
                "SELECT * FROM facts ORDER BY confidence DESC, updated DESC LIMIT ?",
                (max(1, int(limit)),))
        out = []
        for row in rows:
            d = dict(row)
            d["tags"] = _loads(d.get("tags"), [])
            out.append(d)
        return out

    def delete_fact(self, key: str) -> bool:
        return self._execute("DELETE FROM facts WHERE key=?", (key,)).rowcount > 0

    # --------------------------------------------------------- skill nodes
    def replace_skill_nodes(self, nodes: list[dict]) -> int:
        now = time.time()
        with self._lock:
            self._conn.execute("DELETE FROM skill_nodes")
            for n in nodes:
                self._conn.execute(
                    """INSERT INTO skill_nodes(path, name, title, description, parent,
                       tags, capabilities, mtime, size, hash, health, updated)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (n.get("path"), n.get("name"), n.get("title"), n.get("description"),
                     n.get("parent"), _dumps(n.get("tags") or []),
                     _dumps(n.get("capabilities") or []), n.get("mtime"),
                     n.get("size"), n.get("hash"), _dumps(n.get("health") or []), now),
                )
            self._conn.commit()
        return len(nodes)

    def list_skill_nodes(self) -> list[dict]:
        out = []
        for row in self._query("SELECT * FROM skill_nodes ORDER BY path"):
            d = dict(row)
            d["tags"] = _loads(d.get("tags"), [])
            d["capabilities"] = _loads(d.get("capabilities"), [])
            d["health"] = _loads(d.get("health"), [])
            out.append(d)
        return out

    # -------------------------------------------------------- capabilities
    def list_capabilities(self, limit: int = 500, category: str | None = None,
                          status: str | None = None, query: str = "") -> list[dict]:
        sql = "SELECT * FROM capabilities WHERE 1=1"
        params: list[Any] = []
        if category:
            sql += " AND category=?"
            params.append(category)
        if status:
            sql += " AND status=?"
            params.append(status)
        if query:
            like = f"%{query}%"
            sql += " AND (label LIKE ? OR how LIKE ? OR keywords LIKE ? OR id LIKE ?)"
            params.extend([like, like, like, like])
        sql += " ORDER BY category, id LIMIT ?"
        params.append(max(1, int(limit)))
        return [dict(r) for r in self._query(sql, params)]

    def get_capability(self, cap_id: str) -> dict | None:
        row = self._one("SELECT * FROM capabilities WHERE id=?", (cap_id,))
        return dict(row) if row else None

    def set_capability(self, cap_id: str, status: str, evidence: str = "",
                       notes: str | None = None, source: str = "auto") -> bool:
        now = time.time()
        existing = self.get_capability(cap_id)
        if not existing:
            return False
        confirmed_at = now if status in ("confirmed", "learned") else existing.get("last_confirmed")
        self._execute(
            """UPDATE capabilities SET status=?, evidence=?, notes=COALESCE(?, notes),
               last_checked=?, last_confirmed=?, source=? WHERE id=?""",
            (status, self._safe(evidence, 800), notes, now, confirmed_at,
             source, cap_id),
        )
        self.add_event("capability", cap_id, {"status": status,
                                              "evidence": self._safe(evidence, 200)})
        return True

    # -------------------------------------------------------------- events
    def add_event(self, kind: str, subject: str = "", detail: Any = None) -> int:
        cur = self._execute(
            "INSERT INTO events(ts, kind, subject, detail) VALUES(?,?,?,?)",
            (time.time(), kind, self._safe(subject, 300),
             _dumps(privacy.redact_obj(detail, 500) if self.privacy_cfg.get("redact", True) else detail)),
        )
        return int(cur.lastrowid)

    def list_events(self, limit: int = 100) -> list[dict]:
        rows = self._query("SELECT * FROM events ORDER BY id DESC LIMIT ?",
                           (max(1, int(limit)),))
        out = []
        for row in rows:
            d = dict(row)
            d["detail"] = _loads(d.get("detail"), {})
            out.append(d)
        return out

    # --------------------------------------------------------------- search
    def _index(self, kind: str, ref: int, text: str) -> None:
        if not self._fts or not text.strip():
            return
        with self._lock:
            try:
                self._conn.execute("DELETE FROM memory_fts WHERE kind=? AND ref=?",
                                   (kind, str(ref)))
                self._conn.execute("INSERT INTO memory_fts(kind, ref, text) VALUES(?,?,?)",
                                   (kind, str(ref), text[:8000]))
                self._conn.commit()
            except sqlite3.Error:
                pass

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = [t for t in query.replace('"', " ").split() if len(t) > 1]
        return " OR ".join(f'"{t}"' for t in tokens[:12])

    def search(self, query: str, limit: int = 30) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        results: list[dict] = []
        if self._fts:
            fts_q = self._fts_query(query)
            if fts_q:
                try:
                    rows = self._query(
                        """SELECT kind, ref, text, bm25(memory_fts) AS score
                           FROM memory_fts WHERE memory_fts MATCH ?
                           ORDER BY score LIMIT ?""",
                        (fts_q, max(1, int(limit))),
                    )
                    for r in rows:
                        results.append({"kind": r["kind"], "ref": r["ref"],
                                        "text": r["text"], "score": abs(float(r["score"]))})
                    if results:
                        return results
                except sqlite3.Error:
                    pass
        like = f"%{query}%"
        for table, kind, cols in (
            ("episodes", "episode", "request"),
            ("recipes", "recipe", "title"),
            ("anti_patterns", "mistake", "symptom"),
            ("facts", "fact", "value"),
            ("habits", "habit", "subject"),
        ):
            rows = self._query(
                f"SELECT id, {cols} AS text FROM {table} WHERE {cols} LIKE ? LIMIT ?",
                (like, max(1, int(limit))),
            )
            for r in rows:
                results.append({"kind": kind, "ref": str(r["id"]),
                                "text": r["text"], "score": 0.0})
        return results[:limit]

    def reindex(self) -> int:
        if not self._fts:
            return 0
        with self._lock:
            self._conn.execute("DELETE FROM memory_fts")
            count = 0
            for row in self._conn.execute("SELECT id, request, response FROM episodes"):
                text = " ".join(filter(None, [row["request"], row["response"]]))
                if text.strip():
                    self._conn.execute(
                        "INSERT INTO memory_fts(kind, ref, text) VALUES(?,?,?)",
                        ("episode", str(row["id"]), text[:8000]))
                    count += 1
            for row in self._conn.execute("SELECT id, title, intent, notes FROM recipes"):
                text = " ".join(filter(None, [row["title"], row["intent"], row["notes"]]))
                if text.strip():
                    self._conn.execute(
                        "INSERT INTO memory_fts(kind, ref, text) VALUES(?,?,?)",
                        ("recipe", str(row["id"]), text[:8000]))
                    count += 1
            for row in self._conn.execute("SELECT id, symptom, cause, fix FROM anti_patterns"):
                text = " ".join(filter(None, [row["symptom"], row["cause"], row["fix"]]))
                if text.strip():
                    self._conn.execute(
                        "INSERT INTO memory_fts(kind, ref, text) VALUES(?,?,?)",
                        ("mistake", str(row["id"]), text[:8000]))
                    count += 1
            self._conn.commit()
            return count

    # ---------------------------------------------------------------- stats
    def stats(self) -> dict:
        def count(table: str) -> int:
            row = self._one(f"SELECT COUNT(*) AS n FROM {table}")
            return int(row["n"]) if row else 0

        outcomes = {r["outcome"]: int(r["n"]) for r in self._query(
            "SELECT outcome, COUNT(*) AS n FROM episodes GROUP BY outcome")}
        verification = {r["verification_status"]: int(r["n"]) for r in self._query(
            "SELECT verification_status, COUNT(*) AS n FROM episodes "
            "GROUP BY verification_status")}
        last = self._one("SELECT ts FROM episodes ORDER BY id DESC LIMIT 1")
        first = self._one("SELECT ts FROM episodes ORDER BY id ASC LIMIT 1")
        try:
            size = os.path.getsize(self.path)
        except OSError:
            size = 0
        return {
            "db_path": str(self.path),
            "db_size_bytes": size,
            "episodes": count("episodes"),
            "feedback": count("feedback"),
            "recipes": count("recipes"),
            "mistakes": count("anti_patterns"),
            "habits": count("habits"),
            "facts": count("facts"),
            "skills": count("skill_nodes"),
            "capabilities": count("capabilities"),
            "events": count("events"),
            "outcomes": outcomes,
            "verification": verification,
            "verified_episodes": int(verification.get("verified", 0)
                                     + verification.get("user_confirmed", 0)),
            "pending_verification": int(verification.get("unverified", 0)),
            "first_episode_ts": first["ts"] if first else None,
            "last_episode_ts": last["ts"] if last else None,
            "fts": self._fts,
        }

    # --------------------------------------------------------------- prune
    def prune(self, episodes_days: int = 400, events_days: int = 180,
              max_episodes: int = 200000, min_confidence: float = 0.12) -> dict:
        now = time.time()
        removed: dict[str, int] = {}
        cur = self._execute("DELETE FROM episodes WHERE ts < ?",
                            (now - episodes_days * 86400,))
        removed["episodes_old"] = cur.rowcount
        cur = self._execute("DELETE FROM events WHERE ts < ?",
                            (now - events_days * 86400,))
        removed["events_old"] = cur.rowcount
        row = self._one("SELECT COUNT(*) AS n FROM episodes")
        excess = int(row["n"]) - int(max_episodes) if row else 0
        if excess > 0:
            cur = self._execute(
                "DELETE FROM episodes WHERE id IN "
                "(SELECT id FROM episodes ORDER BY id ASC LIMIT ?)", (excess,))
            removed["episodes_excess"] = cur.rowcount
        cur = self._execute(
            "DELETE FROM habits WHERE pinned=0 AND confidence < ? AND last_seen < ?",
            (min_confidence, now - 120 * 86400))
        removed["habits_stale"] = cur.rowcount
        return removed

    # -------------------------------------------------------------- export
    def export_data(self) -> dict:
        def rows(table: str) -> list[dict]:
            return [dict(r) for r in self._query(f"SELECT * FROM {table}")]
        return {
            "format": "mia-learning",
            "version": SCHEMA_VERSION,
            "exported_at": time.time(),
            "episodes": rows("episodes"),
            "feedback": rows("feedback"),
            "recipes": rows("recipes"),
            "anti_patterns": rows("anti_patterns"),
            "habits": rows("habits"),
            "facts": rows("facts"),
            "capabilities": rows("capabilities"),
            "events": rows("events"),
        }

    def import_data(self, data: dict, merge: bool = True) -> dict:
        if (data or {}).get("format") != "mia-learning":
            raise ValueError("not a mia-learning export")
        imported: dict[str, int] = {}
        with self._lock:
            if not merge:
                for table in ("episodes", "feedback", "recipes", "anti_patterns",
                              "habits", "facts", "events"):
                    self._conn.execute(f"DELETE FROM {table}")
            for table in ("recipes", "anti_patterns", "habits", "facts"):
                for row in data.get(table) or []:
                    cols = [c for c in row if c != "id"]
                    placeholders = ",".join("?" for _ in cols)
                    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "key")
                    sql = (f"INSERT INTO {table}({','.join(cols)}) VALUES({placeholders}) "
                           f"ON CONFLICT(key) DO UPDATE SET {updates}")
                    try:
                        self._conn.execute(sql, [row.get(c) for c in cols])
                        imported[table] = imported.get(table, 0) + 1
                    except sqlite3.Error:
                        continue
            for row in data.get("capabilities") or []:
                cols = [c for c in row if c != "id"]
                placeholders = ",".join("?" for _ in cols)
                updates = ",".join(f"{c}=excluded.{c}" for c in cols)
                try:
                    self._conn.execute(
                        f"INSERT INTO capabilities(id,{','.join(cols)}) "
                        f"VALUES(?,{placeholders}) ON CONFLICT(id) DO UPDATE SET {updates}",
                        [row.get("id")] + [row.get(c) for c in cols])
                    imported["capabilities"] = imported.get("capabilities", 0) + 1
                except sqlite3.Error:
                    continue
            for table in ("episodes", "feedback", "events"):
                for row in data.get(table) or []:
                    cols = [c for c in row if c != "id"]
                    placeholders = ",".join("?" for _ in cols)
                    try:
                        self._conn.execute(
                            f"INSERT INTO {table}({','.join(cols)}) VALUES({placeholders})",
                            [row.get(c) for c in cols])
                        imported[table] = imported.get(table, 0) + 1
                    except sqlite3.Error:
                        continue
            self._conn.commit()
        self.reindex()
        return imported

    def backup(self, dest: str | Path) -> Path:
        dest = Path(dest).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self._conn.backup(target)
            finally:
                target.close()
        return dest

    # ---------------------------------------------------------- audit files
    def ingest_audit(self, path: str | Path, source: str = "control") -> int:
        path = Path(path).expanduser()
        if not path.exists():
            return 0
        row = self._one("SELECT offset FROM audit_ingest WHERE path=?", (str(path),))
        offset = int(row["offset"]) if row else 0
        size = path.stat().st_size
        if offset > size:
            offset = 0
        count = 0
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            fh.seek(offset)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ok = bool(rec.get("ok"))
                verification = rec.get("verification") or {}
                verified = bool(rec.get("verified")) or verification.get("status") == "verified"
                verification_status = (verification.get("status")
                                       or ("verified" if verified else
                                           ("failed" if not ok else "unverified")))
                self.record_episode(
                    ts=rec.get("ts") or time.time(),
                    session=rec.get("session") or "control",
                    source=source,
                    intent=str(rec.get("action") or ""),
                    request=str(rec.get("action") or "") + " " + " ".join(
                        map(str, rec.get("args") or [])),
                    response=str(rec.get("error") or rec.get("summary") or ""),
                    steps=[{"action": rec.get("action"), "args": rec.get("args"),
                            "ok": ok, "rc": rec.get("rc")}],
                    outcome="success" if ok else "failure",
                    verified=verified,
                    verification_status=verification_status,
                    verification=verification,
                    error=rec.get("error") or "",
                    duration_s=(rec.get("ms") or 0) / 1000.0,
                    tags=["control", str(rec.get("action") or "")],
                    meta={"host": rec.get("host"), "cwd": rec.get("cwd")},
                )
                try:
                    from . import capabilities as _caps
                    _caps.mark_learned(self, str(rec.get("action") or ""), ok)
                except Exception:
                    pass
                count += 1
            new_offset = fh.tell()
        self._execute(
            """INSERT INTO audit_ingest(path, offset, updated) VALUES(?,?,?)
               ON CONFLICT(path) DO UPDATE SET offset=excluded.offset,
                 updated=excluded.updated""",
            (str(path), new_offset, time.time()),
        )
        if count:
            self.add_event("audit_ingest", str(path), {"records": count})
        return count
