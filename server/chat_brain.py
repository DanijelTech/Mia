"""Fast conversational brain, separate from the Hermes agent.

The chat model answers small talk and general questions directly. Anything that
looks like an action, a live-data question or a URL/path is left to Hermes. The
model can also veto a misroute by replying with the ``[[AGENT]]`` sentinel.

Only the pure routing helper lives in ``mia_core.integration``; this module adds
the OpenAI-compatible streaming client. ``requests`` is imported lazily so the
module stays importable in the stdlib-only test container.
"""

from __future__ import annotations

import json
import os
import time
from typing import Iterator

from mia_core.brain import classify_brain

SENTINEL = "[[AGENT]]"

# One compact paragraph so the chat model knows what Mia can do without being
# given tool schemas (it must not execute anything itself).
CAPABILITIES = (
    "poiskati po Googlu in odpreti rezultate, predvajati glasbo na YouTube, "
    "povedati uro in datum, vreme, odpreti in zapreti aplikacije ter okna, "
    "upravljati datoteke, posnetke zaslona, glasnost, svetlost, opomnike, "
    "opravila in sistemske ukaze"
)

DEFAULT_SYSTEM = (
    "Govoriš kot Mia, slovenski glasovni pomočnik. Odgovarjaj v slovenščini, "
    "mirno in naravno, kot v pogovoru — ne naštevaj korakov in ne opisuj "
    "orodij. Prva poved naj ima največ 8 besed; skupaj 1–3 kratke povedi. "
    "Brez markdowna, seznamov in kodnih blokov. "
    f"Znaš: {CAPABILITIES}. "
    "Če uporabnik zahteva dejanje na računalniku, ne odgovarjaj sam: vrni "
    "točno [[AGENT]]."
)


class EscalateToAgent(RuntimeError):
    """The chat model decided the turn needs the agent's tools."""


class ChatBrain:
    """Streaming client for the small local chat model (llama.cpp compatible)."""

    def __init__(self, cfg: dict):
        llm = cfg.get("llm") or {}
        router = llm.get("router") or {}
        self.router_enabled = bool(router.get("enabled", False))
        self.cfg = llm.get("chat") or {}
        self.enabled = bool(self.router_enabled
                            and self.cfg.get("enabled", False)
                            and self.cfg.get("base_url"))
        self._history: dict[str, list[dict]] = {}

    def choose(self, text: str) -> str:
        """Return ``"chat"`` or ``"agent"`` for one turn."""
        if not self.enabled:
            return "agent"
        return classify_brain(text)

    def _history_for(self, conversation: str) -> list[dict]:
        return self._history.setdefault(conversation, [])

    def recent(self, conversation: str = "mia-main", turns: int = 2) -> str:
        """Compact last-N-turn transcript for hand-off to the agent."""
        history = self._history_for(conversation)[-2 * max(1, turns):]
        lines = []
        for msg in history:
            role = "Uporabnik" if msg.get("role") == "user" else "Mia"
            text = str(msg.get("content") or "").strip().replace("\n", " ")
            if text:
                lines.append(f"{role}: {text[:200]}")
        return "\n".join(lines)

    def note(self, conversation: str, user: str, assistant: str) -> None:
        """Record an agent turn so the next chat turn keeps the context."""
        user = (user or "").strip()
        assistant = (assistant or "").strip()
        if not user or not assistant:
            return
        hist = self._history_for(conversation)
        hist.append({"role": "user", "content": user[:1000]})
        hist.append({"role": "assistant", "content": assistant[:2000]})
        keep = max(2, int(self.cfg.get("history_turns", 8)) * 2)
        del hist[:-keep]

    def _messages(self, transcript: str, conversation: str,
                  brief: str = "") -> list[dict]:
        cfg = self.cfg
        messages = [{"role": "system",
                     "content": cfg.get("system_prompt") or DEFAULT_SYSTEM}]
        if brief:
            limit = int(cfg.get("brief_chars", 400))
            messages.append({"role": "system",
                             "content": "[MIA SPOMIN]\n" + brief[:limit]})
        messages.extend(self._history_for(conversation))
        messages.append({"role": "user", "content": transcript})
        return messages

    def _request(self, messages: list[dict]):
        import requests  # lazy: keeps this module importable without deps
        cfg = self.cfg
        url = str(cfg["base_url"]).rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        key_env = cfg.get("api_key_env")
        if key_env and os.environ.get(key_env):
            headers["Authorization"] = f"Bearer {os.environ[key_env]}"
        payload = {
            "model": cfg.get("model") or "local-chat",
            "messages": messages,
            "stream": True,
            "max_tokens": int(cfg.get("max_tokens", 160)),
            "temperature": float(cfg.get("temperature", 0.6)),
        }
        return requests.post(url, json=payload, headers=headers, stream=True,
                             timeout=float(cfg.get("timeout", 30)))

    # --- streaming turn -------------------------------------------------

    def stream(self, transcript: str, conversation: str = "mia-main",
               brief: str = "", timing=None) -> Iterator[tuple[str, str]]:

        cfg = self.cfg
        resp = self._request(self._messages(transcript, conversation, brief))
        parts: list[str] = []
        guard = ""
        decided = False
        escalated = False
        try:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue


                data = line[5:].strip()
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                for choice in obj.get("choices") or []:
                    text = ((choice.get("delta") or {}).get("content") or "")
                    if not text:
                        continue
                    if not decided:
                        guard += text
                        probe = guard.strip().upper()
                        if SENTINEL.startswith(probe) and len(probe) < len(SENTINEL):
                            continue
                        if probe.startswith(SENTINEL):
                            escalated = True
                            break
                        decided = True
                        parts.append(guard)
                        if timing is not None and timing.llm_first_token_monotonic is None:
                            timing.llm_first_token_monotonic = time.perf_counter()
                        yield ("text", guard)
                        guard = ""
                        continue
                    parts.append(text)
                    if timing is not None and timing.llm_first_token_monotonic is None:
                        timing.llm_first_token_monotonic = time.perf_counter()
                    yield ("text", text)
                if escalated:
                    break
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if escalated:
            raise EscalateToAgent()
        if guard:
            parts.append(guard)
            yield ("text", guard)
        answer = "".join(parts).strip()
        if answer:
            hist = self._history_for(conversation)
            hist.append({"role": "user", "content": transcript})
            hist.append({"role": "assistant", "content": answer})
            keep = max(2, int(cfg.get("history_turns", 8)) * 2)
            del hist[:-keep]

    def reply(self, transcript: str, conversation: str = "mia-main",
              brief: str = "") -> str:
        return "".join(value for _, value in
                       self.stream(transcript, conversation, brief)).strip()
