"""Redaction helpers: durable memory must never store secrets verbatim."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS = [
    re.compile(r"\b(?:api[_-]?key|secret|password|passwd|token|bearer|authorization)\b\s*[:=]\s*\S+", re.I),
    re.compile(r"\b(?:sk|pk|key|tok|ghp|xox[abp])[-_][A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\b[A-Za-z0-9+/_\-]{40,}\b"),
    re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.S),
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\+?\d[\d\s\-]{7,}\d)\b"),          # phone-like numbers
    re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),  # card-like numbers
]

_REDACTED = "[REDACTED]"


def redact(text: str, max_chars: int | None = None) -> str:
    if not text:
        return ""
    out = str(text)
    for pattern in _PATTERNS:
        out = pattern.sub(_REDACTED, out)
    if max_chars is not None and len(out) > max_chars:
        out = out[: max(0, max_chars - 1)] + "…"
    return out


def redact_obj(value: Any, max_chars: int | None = None) -> Any:
    if isinstance(value, str):
        return redact(value, max_chars)
    if isinstance(value, dict):
        return {str(k): redact_obj(v, max_chars) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_obj(v, max_chars) for v in value]
    return value


def clip(text: str, max_chars: int) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= max_chars else text[: max(0, max_chars - 1)] + "…"
