#!/usr/bin/env python3
"""Hermes LAN voice pipeline server (v3 — sessions, stop, approvals, partials).

WebSocket protocol (client → server):
  {"type":"start", "sample_rate":16000, "format":"pcm_s16le", "channels":1,
   "conversation": "mia-main"?}          begin a turn (mid-turn = barge-in)
  <binary int16 16 kHz mono PCM chunks>
  {"type":"stop"}                            end of speech, process turn
  {"type":"stop_run"}                        halt the running agent turn
  {"type":"approval_decision", "run_id":..., "approval_id":..., "decision":"allow"|"deny"}

Server → client JSON events:
  status, transcript, partial_transcript, agent_status{thinking|tool_use|speaking},
  run_started{run_id}, approval_request{...}, error, done{timing}
plus binary 16 kHz mono int16 PCM TTS audio.

Brain: Hermes Agent API server via the Sessions API (/api/sessions/{id}/chat/stream),
which provides persistent conversation memory, run ids (stoppable), tool events,
and approval events. Falls back to direct Anthropic ("basic mode") if unreachable.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import random
import shutil
import subprocess
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Iterator

import requests
import uvicorn
import yaml
import numpy as np
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

try:  # newer starlette raises a distinct error on receive-after-disconnect
    from starlette.websockets import WebSocketDisconnected
except ImportError:  # pragma: no cover
    WebSocketDisconnected = WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from RealtimeSTT import AudioToTextRecorder

from continuous import WakeGate, build_segmenter, starts_with_exact_wake
from speaker_gate import SpeakerGate
from tts import build_backend

try:
    import psutil
except ImportError:  # machines panel degrades gracefully
    psutil = None


def _anthropic_client(key: str):
    """Imported lazily: offline installs do not need the SDK at all."""
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed (offline mode needs no fallback)") from exc
    return Anthropic(api_key=key)

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "server.yaml"
LOG_PATH = ROOT / "logs" / "latency.jsonl"
STATE_PATH = ROOT / "logs" / "hermes_sessions.json"
USAGE_PATH = ROOT / "logs" / "usage_stats.json"
_USAGE_LOCK = threading.Lock()


class BackendUnavailable(RuntimeError):
    """Hermes gateway or its key is unusable; the message is user-friendly."""


def friendly_error(exc: BaseException) -> str:
    """One actionable sentence for the HUD; the full traceback stays in the log."""
    base = ((CFG.get("hermes") or {}).get("base_url") or "http://127.0.0.1:8642")
    text = str(exc) or exc.__class__.__name__
    low = text.lower()
    if ("connection refused" in low or "max retries exceeded" in low
            or "failed to establish a new connection" in low
            or isinstance(exc, requests.exceptions.ConnectionError)):
        return (f"Hermesov gateway ni dosegljiv na {base} — zaženi `hermes gateway` "
                f"(preveri tudi API_SERVER_ENABLED/KEY v ~/.hermes/.env).")
    if "api key not found" in low:
        return ("Mia ne vidi Hermesovega ključa — dodaj API_SERVER_KEY v ~/.hermes/.env "
                "in znova zaženi Mio (systemctl --user restart mia-voice).")
    if "401" in low:
        return "Hermes je zavrnil ključ (401) — API_SERVER_KEY v ~/.hermes/.env se ne ujema."
    first = text.strip().splitlines()[0]
    return first[:300]


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def pick_stt_device(requested: str, min_free_gb: float = 2.5) -> str:
    """`auto` = CUDA only when a GPU currently has room for Whisper, else CPU."""
    requested = (requested or "auto").lower()
    if requested in ("cpu", "cuda"):
        return requested
    try:
        import torch  # RealtimeSTT already pulls torch; import errors mean no GPU stack
    except Exception:
        return "cpu"
    try:
        if not torch.cuda.is_available():
            return "cpu"
        free, _total = torch.cuda.mem_get_info()
        free_gb = free / 1024**3
        if free_gb < min_free_gb:
            print(f"STT: {free_gb:.1f} GB VRAM free (< {min_free_gb} GB) -> CPU/RAM", flush=True)
            return "cpu"
        print(f"STT: {free_gb:.1f} GB VRAM free -> CUDA", flush=True)
        return "cuda"
    except Exception:
        return "cpu"


def _env_first(*names: str) -> str:
    """First non-empty environment value (MIA_* first, then pre-rebrand JARVIS_*)."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def record_usage(llm_in: int = 0, llm_out: int = 0, turns: int = 0, tts_chars: int = 0) -> None:
    """Accumulate token/character usage into logs/usage_stats.json (total + per-day)."""
    with _USAGE_LOCK:
        try:
            data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {"total": {}, "days": {}}
        day = data["days"].setdefault(_today(), {})
        for bucket in (data["total"], day):
            bucket["llm_in"] = bucket.get("llm_in", 0) + llm_in
            bucket["llm_out"] = bucket.get("llm_out", 0) + llm_out
            bucket["turns"] = bucket.get("turns", 0) + turns
            bucket["tts_chars"] = bucket.get("tts_chars", 0) + tts_chars
        # keep last 60 days
        for k in sorted(data["days"])[:-60]:
            del data["days"][k]
        USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        USAGE_PATH.write_text(json.dumps(data), encoding="utf-8")


def read_usage() -> dict:
    with _USAGE_LOCK:
        try:
            data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {"total": {}, "days": {}}
    return {"total": data.get("total", {}), "today": data.get("days", {}).get(_today(), {})}
ENV_PATHS = [Path.home() / ".hermes" / ".env", ROOT / ".env"]
SENTENCE_RE = re.compile(r"(.+?[.!?])(?=\s|$)", re.DOTALL)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
CODEBLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
# Secret-shaped strings are never sent to cloud TTS (privacy filter):
SECRET_RES = [
    re.compile(r"\b(?:api[_-]?key|secret|password|passwd|token|bearer|authorization)\b\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|key|tok|ghp|xox[abp])[-_][A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\b[A-Za-z0-9+/_\-]{36,}\b"),          # long opaque blobs (keys, JWT segments)
    re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL),
]


def load_env() -> None:
    for path in ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


ENROLL_PHRASES = (
    "prepoznaj glas", "prepoznaj moj glas", "zapomni si moj glas",
    "zapomni moj glas", "nauči se moj glas", "nauci se moj glas",
    "shrani moj glas", "vpiši moj glas", "vpisi moj glas",
)

MEDIA_STOP_PHRASES = (
    "ustavi glasbo", "zaustavi glasbo", "ugasni glasbo", "dovolj glasbe",
    "ustavi muziko", "zaustavi muziko", "ugasni muziko",
    "ustavi pesem", "ustavi predvajanje", "zaustavi predvajanje",
    "ustavi video", "ustavi film", "počisti zaslon", "pocisti zaslon",
    "umakni z zaslona", "ugasni panel",
)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-zčšžćđ ]+", " ", (text or "").lower())).strip()


def _is_enroll_command(text: str) -> bool:
    """'Mia, prepoznaj glas!' — voice-triggered enrollment of the utterance."""
    flat = _flat(text)
    return any(p in flat for p in ENROLL_PHRASES)


def _is_media_stop(text: str) -> bool:
    """'Mia, ustavi predvajanje (v ozadju)!' — deterministic media stop."""
    flat = _flat(text)
    return any(p in flat for p in MEDIA_STOP_PHRASES)


def _is_media_open_browser(text: str) -> bool:
    """'Mia, predvajanje iz ozadja odpri v brskalniku!' — move the current
    panel media into a visible desktop window."""
    flat = _flat(text)
    if "brskalnik" in flat and any(k in flat for k in
            ("predvajanje", "glasbo", "glasba", "muziko", "film", "video", "ozadja", "ozadju", "panel")):
        return True
    return "iz ozadja" in flat and ("odpri" in flat or "pokaži" in flat or "pokazi" in flat)


def _volume_request(text: str) -> list[str] | None:
    """'Mia, pojačaj (za 20)!' / 'glasnost na 50' / 'zmanjšaj' -> mia-volume args."""
    flat = re.sub(r"\s+", " ", re.sub(r"[^a-zčšžćđ0-9 ]+", " ", (text or "").lower())).strip()
    m = re.search(r"glasnost(?:i)?(?:\s+na)?\s+(\d+)", flat)
    if m:
        return ["set", m.group(1)]
    if "koliko je glasnosti" in flat or "kakšna je glasnost" in flat:
        return ["status"]
    m = re.search(r"poja[cč]aj(?:\s+za)?\s*(\d+)?", flat)
    if m or "glasneje" in flat:
        pct = (m.group(1) if m else None)
        return ["up"] + ([pct] if pct else [])
    m = re.search(r"(?:zmanj[sš]aj|zni[zž]aj|uti[sš]aj)(?:\s+za)?\s*(\d+)?", flat)
    if m or " ti[sš]e" in flat or flat.endswith("ti[sš]e"):
        pct = (m.group(1) if m else None)
        return ["down"] + ([pct] if pct else [])
    if "ugasni zvok" in flat or "brez zvoka" in flat:
        return ["mute"]
    return None


def _fav_artist_match(query: str) -> str | None:
    """Fuzzy-match a spoken name against the favorites list ('snupi dog' ->
    'Snoop Dogg'). Used when a play request has no explicit music keyword."""
    import difflib
    try:
        artists = [a.strip() for a in
                   (Path.home() / ".config" / "mia" / "favorite-artists.txt")
                   .read_text(encoding="utf-8").splitlines() if a.strip()]
    except OSError:
        return None
    best, score = None, 0.0
    for a in artists:
        r = difflib.SequenceMatcher(None, query, a.lower()).ratio()
        if r > score:
            best, score = a, r
    return best if score >= 0.7 else None


def _music_play_request(text: str) -> str | None:
    """'Mia, pusti mi glazbo (v ozadju)!' / 'Mia, poišči X in ga predvajaj!'

    Returns the search query, '' when a favorite artist should be picked,
    or None when this is not a music-play request."""
    flat = _flat(text)
    if not any(w in flat for w in ("glazb", "muzik", "glasb", "pesem", "pesm", "predvajaj")):
        # no music keyword: only "pusti (mi) <ime>" with a fuzzy favorite match
        m = re.match(r"^pusti(?:te)?(?:\s+mi)?\s+(.+)$", flat)
        if m:
            q = re.sub(r"\s+", " ", m.group(1)).strip()
            return _fav_artist_match(q)
        return None
    m = (re.match(r"^(?:poi[sš][cč]i|najdi|na[đd]i|prona[đd]i)\s+(.+)$", flat)
         or re.match(r"^pusti(?:te)?(?:\s+mi)?\s+(.+)$", flat)
         or re.match(r"^zaigraj(?:\s+mi)?\s+(.+)$", flat))
    if not m:
        return None
    q = m.group(1)
    for junk in ("v ozadju", "iz ozadja", "enega od izvajalcev", "od izvajalca",
                 "izvajalcev", "izvajalca", "in ga predvajaj", "ter ga predvajaj",
                 "in jo predvajaj", "ter jo predvajaj", "predvajaj", "glazbo",
                 "glasbo", "muziko", "glasba", "glazba", "muzika", "pesem",
                 "pesmo", "nekaj", "neko", "eno", "malce", "prosim", "spet",
                 "ponovno", "kakšno", "kaksno"):
        q = q.replace(junk, " ")
    q = re.sub(r"^od\s+", "", q.strip())   # "od Cece" -> "cece"
    return re.sub(r"\s+", " ", q).strip()


def _pick_favorite_artist() -> str:
    try:
        artists = [a.strip() for a in
                   (Path.home() / ".config" / "mia" / "favorite-artists.txt")
                   .read_text(encoding="utf-8").splitlines() if a.strip()]
    except OSError:
        artists = []
    return random.choice(artists) if artists else "slovenska glasba"


async def _stop_all_media() -> None:
    """Stop every playback path: HUD panels + desktop media windows.
    Called before starting a new track — never two songs at once."""
    for client in list(WS_CLIENTS):
        try:
            await client.send_json({"type": "dismiss_panels"})
        except Exception:
            WS_CLIENTS.discard(client)
    ACTIVE_PANELS.clear()
    try:
        await asyncio.to_thread(subprocess.run, ["mia-close", "youtube"],
                                capture_output=True, timeout=15)
    except Exception:
        pass


async def _summon_media(src: str, title: str, media: str = "video",
                        position: str = "center") -> int:
    """Show media on every connected HUD (tracked for voice control)."""
    ACTIVE_PANELS.add(src)
    LAST_SUMMON.update(media=media, src=src, title=title)
    payload = {"type": "summon_panel", "media": media, "src": src,
               "title": title[:48], "position": position}
    sent = 0
    for client in list(WS_CLIENTS):
        try:
            await client.send_json(payload)
            sent += 1
        except Exception:
            WS_CLIENTS.discard(client)
    return sent


def _playback_active() -> bool:
    """Is media likely playing? Either a Mia-opened desktop window (registry)
    is still alive, or a holographic panel is up on the HUD. Loud playback
    drowns the voiceprint, so then an explicit wake word may carry the turn.
    Deliberately NOT based on PipeWire stream state: the HUD's own
    AudioContext keeps a Chrome stream non-corked even in silence."""
    if ACTIVE_PANELS:
        return True
    reg = Path.home() / ".cache" / "mia-windows"
    try:
        lines = reg.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":1")
    env.setdefault("XAUTHORITY", f"/run/user/{os.getuid()}/gdm/Xauthority")
    for line in lines:
        wid = line.split("\t", 1)[0].strip()
        if not wid:
            continue
        try:
            r = subprocess.run(["xdotool", "getwindowname", wid],
                               capture_output=True, timeout=2, env=env)
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


@dataclass
class TurnTiming:
    turn_id: int
    audio_start_monotonic: float | None = None
    end_of_speech_monotonic: float | None = None
    stt_start_monotonic: float | None = None
    stt_final_monotonic: float | None = None
    llm_start_monotonic: float | None = None
    llm_first_token_monotonic: float | None = None
    first_sentence_monotonic: float | None = None
    tts_request_start_monotonic: float | None = None
    first_tts_audio_byte_monotonic: float | None = None
    total_done_monotonic: float | None = None
    transcript: str = ""
    response_text: str = ""
    stt_model: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    tts_model: str = ""
    voice_id: str = ""
    run_id: str = ""
    interrupted: bool = False
    tools_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        eos = self.end_of_speech_monotonic
        return {
            "turn_id": self.turn_id,
            "transcript": self.transcript,
            "response_text": self.response_text,
            "stt_model": self.stt_model,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "tts_model": self.tts_model,
            "voice_id": self.voice_id,
            "run_id": self.run_id,
            "interrupted": self.interrupted,
            "tools_used": self.tools_used,
            "stt_finalize_seconds": self._delta(self.stt_start_monotonic, self.stt_final_monotonic),
            "llm_time_to_first_token_seconds": self._delta(self.llm_start_monotonic, self.llm_first_token_monotonic),
            "time_to_first_tts_audio_byte_seconds": self._delta(self.tts_request_start_monotonic, self.first_tts_audio_byte_monotonic),
            "end_of_speech_to_first_audio_seconds": self._delta(eos, self.first_tts_audio_byte_monotonic),
            "total_turn_seconds": self._delta(eos, self.total_done_monotonic),
            "errors": self.errors,
        }

    @staticmethod
    def _delta(start: float | None, end: float | None) -> float | None:
        if start is None or end is None:
            return None
        return round(end - start, 4)


# ===================================================================== Hermes


class HermesAPI:
    """Thin client for the Hermes Agent API server (sessions, runs, approvals)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg.get("hermes") or {}

    @property
    def base(self) -> str:
        return (self.cfg.get("base_url") or "http://127.0.0.1:8642").rstrip("/")

    def headers(self) -> dict:
        key = os.environ.get(self.cfg.get("api_key_env", "API_SERVER_KEY"), "")
        if not key:
            raise RuntimeError(
                "Hermes API key not found in environment: set API_SERVER_KEY in "
                "~/.hermes/.env (of the user running Mia), then restart Mia — "
                "`systemctl --user restart mia-voice`")
        h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if self.cfg.get("session_key"):
            h["X-Hermes-Session-Key"] = self.cfg["session_key"]
        return h

    # ---- persistent named sessions ----
    def _load_state(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: dict) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state), encoding="utf-8")

    def get_session_id(self, name: str, force_new: bool = False) -> str:
        state = self._load_state()
        sid = state.get(name)
        if sid and not force_new:
            return sid
        r = requests.post(f"{self.base}/api/sessions", headers=self.headers(),
                          json={"title": name}, timeout=15)
        r.raise_for_status()
        data = r.json()
        sid = (data.get("session") or data).get("id")
        state[name] = sid
        self._save_state(state)
        print(f"Created Hermes session '{name}' -> {sid}", flush=True)
        return sid

    def stop_run(self, run_id: str) -> dict:
        r = requests.post(f"{self.base}/v1/runs/{run_id}/stop", headers=self.headers(), timeout=15)
        return {"status_code": r.status_code, "body": r.text[:300]}

    def post_approval(self, run_id: str, body: dict) -> dict:
        r = requests.post(f"{self.base}/v1/runs/{run_id}/approval", headers=self.headers(),
                          json=body, timeout=15)
        return {"status_code": r.status_code, "body": r.text[:300]}

    def chat_stream_events(self, session_id: str, input_text: str, timeout: float) -> Iterator[tuple[str, str]]:
        """Yield ("run"|"text"|"tool"|"approval"|"final", value) from a session turn."""
        resp = requests.post(
            f"{self.base}/api/sessions/{session_id}/chat/stream",
            headers={**self.headers(), "Accept": "text/event-stream"},
            json={"input": input_text}, stream=True, timeout=(10, timeout),
        )
        if resp.status_code >= 400:
            resp.close()
            raise RuntimeError(f"Hermes session chat HTTP {resp.status_code}: {resp.text[:300]}")
        resp.encoding = "utf-8"  # SSE has no charset header; requests would assume latin-1 (mojibake)
        try:
            yield from self._parse_sse(resp)
        finally:
            resp.close()  # leaked FDs killed the server once (launchd limit is tiny)

    @staticmethod
    def _parse_sse(resp) -> Iterator[tuple[str, str]]:
        event_name = ""
        for raw in resp.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            if raw.startswith("event: "):
                event_name = raw[7:].strip()
                continue
            if not raw.startswith("data: "):
                continue
            data_text = raw[6:].strip()
            try:
                data = json.loads(data_text)
            except json.JSONDecodeError:
                continue
            ev = event_name or data.get("event", "")
            if ev == "run.started":
                yield ("run", data.get("run_id") or "")
            elif ev == "assistant.delta":
                d = data.get("delta") or ""
                if d:
                    yield ("text", d)
            elif ev == "tool.started":
                name = data.get("tool_name") or "tool"
                if name.startswith("_"):
                    continue  # internal pseudo-tools like _thinking
                yield ("tool", json.dumps({"name": name, "preview": (data.get("preview") or "")[:200]}))
            elif "approval" in ev:
                yield ("approval", json.dumps(data)[:2000])
            elif ev == "assistant.completed":
                yield ("final", json.dumps({
                    "content": data.get("content") or "",
                    "interrupted": bool(data.get("interrupted")),
                }))
            elif ev in ("run.failed", "error"):
                raise RuntimeError(f"Hermes stream error: {data_text[:300]}")
            elif ev == "run.completed":
                usage = data.get("usage") or {}
                if usage:
                    record_usage(
                        llm_in=int(usage.get("input_tokens") or 0),
                        llm_out=int(usage.get("output_tokens") or 0),
                        turns=1,
                    )
            elif ev == "done":
                pass  # stream closes after this


# ==================================================================== Pipeline


class VoicePipelineServer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.turn_counter = 0
        self.hermes = HermesAPI(cfg)
        self.stt_lock = asyncio.Lock()
        stt = cfg["stt"]
        gate_cfg = ((stt.get("continuous") or {}).get("speaker_gate") or {})
        self.speaker_gate: SpeakerGate | None = None
        if gate_cfg.get("enabled", False):
            profile = ROOT / (gate_cfg.get("profile") or "voices/speaker_profile.npz")
            self.speaker_gate = SpeakerGate(
                profile,
                threshold=float(gate_cfg.get("threshold", 0.30)),
                min_seconds=float(gate_cfg.get("min_seconds", 1.0)),
                model=gate_cfg.get("model") or "speechbrain/spkrec-ecapa-voxceleb",
            )
            state = "enrolled" if self.speaker_gate.enrolled else "waiting for enrollment"
            print(f"Speaker gate: on ({state}, threshold {self.speaker_gate.threshold})", flush=True)
        self.stt_language = (stt.get("language") or "en")
        self.stt_device = pick_stt_device(stt.get("device", "auto"),
                                          float(stt.get("min_free_vram_gb", 2.5) or 0))
        compute_type = stt.get("compute_type") or ""
        if compute_type in ("", "auto"):
            compute_type = "float16" if self.stt_device == "cuda" else "int8"
        elif self.stt_device == "cpu" and compute_type in ("float16", "bfloat16"):
            compute_type = "int8"          # fp16 on CPU is unsupported/very slow
        print(f"STT: device={self.stt_device} compute_type={compute_type}", flush=True)
        self.tts = build_backend(cfg, ROOT)
        recorder_kwargs = {
            "model": stt["model"],
            "use_microphone": False,
            "spinner": False,
            "device": self.stt_device,
            "compute_type": compute_type,
            "sample_rate": int(stt.get("sample_rate", 16000)),
            "language": self.stt_language,
            "beam_size": int(stt.get("beam_size", 1)),
            "faster_whisper_vad_filter": False,
            "no_log_file": True,
        }
        if stt.get("initial_prompt"):
            recorder_kwargs["initial_prompt"] = stt["initial_prompt"]
        supported = set(inspect.signature(AudioToTextRecorder).parameters)
        self.recorder = AudioToTextRecorder(
            **{k: v for k, v in recorder_kwargs.items() if k in supported}
        )

    def next_turn_id(self) -> int:
        self.turn_counter += 1
        return self.turn_counter

    def filter_hallucinations(self, text: str) -> str:
        """Drop Whisper's silence/noise hallucinations ('Hvala što pratite' …).

        A transcript that consists ONLY of known hallucination phrases (repeated
        or not) becomes empty; real speech containing them is kept untouched.
        """
        phrases = (self.cfg["stt"].get("hallucination_filter") or [])
        if not text or not phrases:
            return text

        def flat(s: str) -> str:
            return re.sub(r"\s+", " ", re.sub(r"[^a-zčšžćđ0-9 ]+", " ", s.lower())).strip()

        rest = flat(text)
        for phrase in phrases:
            rest = rest.replace(flat(phrase), " ")
        if not flat(rest):
            print(f"STT hallucination dropped: {text[:80]!r}", flush=True)
            return ""
        return text

    async def transcribe(self, audio: bytes, timing: TurnTiming | None = None) -> str:
        if timing:
            timing.stt_start_monotonic = time.perf_counter()
        # 1) GPU worker (if configured and reachable) — big model, ~0.3s
        remote = self.cfg["stt"].get("remote") or {}
        if remote.get("url"):
            text = await asyncio.to_thread(self._remote_stt, audio, remote)
            if text is not None:
                if timing:
                    timing.stt_model = f"remote:{remote.get('name', 'gpu')}"
                    timing.stt_final_monotonic = time.perf_counter()
                return text
        # 2) local Whisper fallback
        sample_rate = int(self.cfg["stt"].get("sample_rate", 16000))
        samples = (np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0).copy()
        try:
            async with self.stt_lock:
                self.recorder.feed_audio(samples, original_sample_rate=sample_rate)
                text = await asyncio.to_thread(self.recorder.perform_final_transcription, samples, True)
                self.recorder.clear_audio_queue()
        except Exception as exc:
            # near-silent audio can make whisper raise ("No clip timestamps found");
            # treat as empty transcript instead of failing the turn
            print(f"local STT error treated as empty transcript: {exc}", flush=True)
            text = ""
        if timing:
            timing.stt_final_monotonic = time.perf_counter()
        return (text or "").strip()

    def _remote_stt(self, audio: bytes, remote: dict) -> str | None:
        """POST raw PCM to the GPU STT worker. None = unavailable (use fallback)."""
        headers = {"Content-Type": "application/octet-stream"}
        token = _env_first(remote.get("token_env", "MIA_HUD_TOKEN"), "JARVIS_HUD_TOKEN")
        if token:
            headers["X-Mia-Token"] = token
        try:
            params = {}
            if self.stt_language:
                params["language"] = self.stt_language
            if (self.cfg["stt"] or {}).get("initial_prompt"):
                params["initial_prompt"] = self.cfg["stt"]["initial_prompt"]
            r = requests.post(remote["url"], data=audio, headers=headers,
                              params=params or None,
                              timeout=float(remote.get("timeout", 6)))
            if r.ok:
                return (r.json().get("text") or "").strip()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ LLM

    def stream_llm_events_sync(
        self, transcript: str, timing: TurnTiming, conversation: str,
    ) -> Iterator[tuple[str, str]]:
        llm = self.cfg["llm"]
        provider = llm["provider"]
        timing.llm_start_monotonic = time.perf_counter()
        if provider == "hermes":
            try:
                h = self.cfg.get("hermes") or {}
                session_id = self.hermes.get_session_id(conversation)
                gen = self._hermes_turn(session_id, transcript, timing, h, conversation)
                first = next(gen)
            except StopIteration:
                return
            except Exception as exc:
                fb = (self.cfg.get("hermes") or {}).get("fallback_provider", "anthropic")
                print(f"Hermes unavailable ({type(exc).__name__}: {exc}); fallback={fb}", flush=True)
                timing.errors.append(f"hermes_fallback: {exc}")
                if not fb:
                    raise BackendUnavailable(friendly_error(exc)) from exc
                yield ("text", "Agent backend offline. Running in basic mode. ")
                provider = fb
            else:
                yield first
                yield from gen
                return
        timing.llm_provider = provider
        timing.llm_model = llm["model"]
        if provider == "anthropic":
            key = os.environ.get(llm.get("api_key_env", "ANTHROPIC_API_KEY"))
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY not found")
            client = _anthropic_client(key)
            with client.messages.stream(
                model=llm["model"],
                max_tokens=int(llm.get("max_tokens", 220)),
                temperature=float(llm.get("temperature", 0.3)),
                system=self.cfg["persona"]["system_prompt"],
                messages=[{"role": "user", "content": transcript}],
            ) as stream:
                for text in stream.text_stream:
                    if text and timing.llm_first_token_monotonic is None:
                        timing.llm_first_token_monotonic = time.perf_counter()
                    yield ("text", text)
        else:
            raise RuntimeError(f"Unsupported LLM provider: {provider}")

    def _hermes_turn(
        self, session_id: str, transcript: str, timing: TurnTiming, h: dict, conversation: str,
    ) -> Iterator[tuple[str, str]]:
        timing.llm_provider = "hermes"
        timing.llm_model = "hermes-agent"
        timeout = float(h.get("timeout", 240))
        directive = (h.get("language_directive") or "").strip()
        payload = f"{directive}\n\n{transcript}" if directive else transcript
        try:
            it = self.hermes.chat_stream_events(session_id, payload, timeout)
            for kind, value in it:
                if kind == "text" and timing.llm_first_token_monotonic is None:
                    timing.llm_first_token_monotonic = time.perf_counter()
                yield (kind, value)
        except RuntimeError as exc:
            # stale session id (e.g. Hermes DB reset) -> recreate once
            if "404" in str(exc):
                session_id = self.hermes.get_session_id(conversation, force_new=True)
                for kind, value in self.hermes.chat_stream_events(session_id, payload, timeout):
                    if kind == "text" and timing.llm_first_token_monotonic is None:
                        timing.llm_first_token_monotonic = time.perf_counter()
                    yield (kind, value)
            else:
                raise

    # ------------------------------------------------------------------ TTS

    def tts_chunks_sync(self, text: str, timing: TurnTiming) -> Iterator[bytes]:
        timing.tts_model = self.tts.label
        timing.voice_id = getattr(self.tts, "voice_id", "") or ""
        timing.tts_request_start_monotonic = timing.tts_request_start_monotonic or time.perf_counter()
        record_usage(tts_chars=len(text))
        for chunk in self.tts.synth(text):
            if timing.first_tts_audio_byte_monotonic is None:
                timing.first_tts_audio_byte_monotonic = time.perf_counter()
            yield chunk

    # ------------------------------------------------------------- Turn flow

    async def stream_response_audio(
        self, ws: WebSocket, transcript: str, timing: TurnTiming, conn: "ConnState",
    ) -> None:
        pending = ""
        full_response: list[str] = []
        spoken = False
        await ws.send_json({"type": "agent_status", "state": "thinking"})

        q: asyncio.Queue = asyncio.Queue()

        async def forward() -> None:
            try:
                async for item in self._async_llm_events(transcript, timing, conn.conversation):
                    await q.put(item)
                await q.put(None)
            except Exception as exc:
                await q.put(exc)

        forward_task = asyncio.create_task(forward())
        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                kind, value = item
                if kind == "run":
                    timing.run_id = value
                    conn.current_run_id = value
                    await ws.send_json({"type": "run_started", "run_id": value})
                    continue
                if kind == "tool":
                    info = json.loads(value)
                    timing.tools_used.append(info.get("name", "tool"))
                    await ws.send_json({"type": "agent_status", "state": "tool_use",
                                        "tool": info.get("name"), "preview": info.get("preview", "")})
                    continue
                if kind == "approval":
                    await ws.send_json({"type": "approval_request", "data": json.loads(value),
                                        "run_id": conn.current_run_id})
                    continue
                if kind == "final":
                    info = json.loads(value)
                    timing.interrupted = info.get("interrupted", False)
                    continue
                # kind == "text"
                full_response.append(value)
                pending += value
                sentences, pending = self._extract_complete_sentences(pending)
                for sentence in sentences:
                    clean = self._clean_for_tts(sentence)
                    if not clean:
                        continue
                    if timing.first_sentence_monotonic is None:
                        timing.first_sentence_monotonic = time.perf_counter()
                    spoken = True
                    conn.spoken_sentences.append(clean)
                    await self._send_tts_sentence(ws, clean, timing, conn)
            tail = self._clean_for_tts(pending.strip())
            if tail:
                conn.spoken_sentences.append(tail)
                await self._send_tts_sentence(ws, tail, timing, conn)
        except BackendUnavailable:
            # nothing was said yet: tell the user out loud instead of staying mute
            if not spoken and not conn.spoken_sentences:
                notice = ((self.cfg.get("hermes") or {}).get("unreachable_text")
                          or "Hermesov gateway ni dosegljiv. Zaženi hermes gateway in poskusi znova.")
                await ws.send_json({"type": "agent_status", "state": "speaking"})
                conn.is_speaking = True
                try:
                    await self._send_tts_sentence(ws, notice, timing)
                except Exception as tts_exc:
                    print(f"could not speak the unreachable notice: {tts_exc}", flush=True)
            raise
        finally:
            if not forward_task.done():
                forward_task.cancel()
        timing.response_text = "".join(full_response).strip()

    async def _async_llm_events(
        self, transcript: str, timing: TurnTiming, conversation: str,
    ) -> AsyncIterator[tuple[str, str]]:
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def worker() -> None:
            try:
                for item in self.stream_llm_events_sync(transcript, timing, conversation):
                    loop.call_soon_threadsafe(q.put_nowait, item)
                loop.call_soon_threadsafe(q.put_nowait, None)
            except Exception as exc:
                loop.call_soon_threadsafe(q.put_nowait, exc)

        worker_task = asyncio.create_task(asyncio.to_thread(worker))
        while True:
            item = await q.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item
        await worker_task

    async def _send_tts_sentence(self, ws: WebSocket, sentence: str, timing: TurnTiming,
                                 conn: "ConnState | None" = None) -> None:
        if not sentence:
            return
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def worker() -> None:
            try:
                for chunk in self.tts_chunks_sync(sentence, timing):
                    loop.call_soon_threadsafe(q.put_nowait, chunk)
                loop.call_soon_threadsafe(q.put_nowait, None)
            except Exception as exc:
                loop.call_soon_threadsafe(q.put_nowait, exc)

        worker_task = asyncio.create_task(asyncio.to_thread(worker))
        while True:
            item = await q.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            if conn is not None and not conn.is_speaking:
                # announce "speaking" only when audio really exists — on a slow
                # CPU TTS the synthesis takes minutes and a premature GOVORIM
                # state reads as "she is mute"
                await ws.send_json({"type": "agent_status", "state": "speaking"})
                conn.is_speaking = True
            await ws.send_bytes(item)
        await worker_task

    @staticmethod
    def _extract_complete_sentences(text: str) -> tuple[list[str], str]:
        sentences = []
        last_end = 0
        for match in SENTENCE_RE.finditer(text):
            sentences.append(match.group(1).strip())
            last_end = match.end()
        return sentences, text[last_end:]

    @staticmethod
    def _clean_for_tts(text: str) -> str:
        if not text:
            return ""
        text = THINK_RE.sub("", text)
        for pattern in SECRET_RES:                  # privacy: never speak secrets
            text = pattern.sub(" redacted ", text)
        text = CODEBLOCK_RE.sub(" code omitted. ", text)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"^[\s>*#-]+", "", text)
        text = re.sub(r"[*_#]{1,3}([^*_#]+)[*_#]{1,3}", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def log_turn(self, timing: TurnTiming) -> None:
        timing.total_done_monotonic = timing.total_done_monotonic or time.perf_counter()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        summary = timing.summary()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")
        print("TURN TIMING", json.dumps(summary, ensure_ascii=False), flush=True)


load_env()
CFG = load_config()
HERMES = HermesAPI(CFG)   # lightweight API client - independent of the STT pipeline
PIPELINE: VoicePipelineServer | None = None

# live voice settings (HUD pitch slider) — persisted across restarts
VOICE_SETTINGS_PATH = ROOT / "logs" / "voice_settings.json"
try:
    VOICE_SETTINGS: dict = json.loads(VOICE_SETTINGS_PATH.read_text(encoding="utf-8"))
except Exception:
    VOICE_SETTINGS = {"pitch_semitones": 0.0}


_PIPELINE_LOCK = threading.Lock()


def get_pipeline() -> VoicePipelineServer:
    """Lock prevents the four uvicorn listeners' startup hooks from racing
    into concurrent recorder inits (which crashed three of the four lifespans
    and silently killed the TLS ports)."""
    global PIPELINE
    if PIPELINE is None:
        with _PIPELINE_LOCK:
            if PIPELINE is None:
                PIPELINE = VoicePipelineServer(CFG)
                # the HUD pitch slider reaches the TTS service per request
                PIPELINE.tts.pitch_getter = lambda: VOICE_SETTINGS.get("pitch_semitones", 0.0)
    return PIPELINE


app = FastAPI(title="Hermes Voice Pipeline")


@app.on_event("startup")
async def warm_pipeline() -> None:
    """Warm the local Whisper fallback in the BACKGROUND, exactly once (this
    hook fires once per uvicorn listener — there are four), and never let a
    warm failure take a listener down."""
    global _WARM_STARTED
    if _WARM_STARTED:
        return
    _WARM_STARTED = True

    async def warm() -> None:
        try:
            await asyncio.to_thread(get_pipeline)
            print("STT pipeline warmed.", flush=True)
        except Exception as exc:
            print(f"STT warm failed (remote STT still available): {exc}", flush=True)

    asyncio.get_running_loop().create_task(warm())


_WARM_STARTED = False


# ------------------------------------------------------------------ Auth

# jarvis.* entries keep pre-rebrand certificate/hostname setups working
ALLOWED_ORIGIN_HOSTS = {"mia.local", "mia", "localhost", "127.0.0.1",
                        "jarvis.local", "jarvis"}
ALLOWED_ORIGIN_HOSTS |= set((CFG.get("security") or {}).get("extra_origin_hosts") or [])


def hud_token() -> str | None:
    env_name = (CFG.get("security") or {}).get("hud_token_env", "MIA_HUD_TOKEN")
    legacy = env_name.replace("MIA_", "JARVIS_", 1) if env_name.startswith("MIA_") else ""
    return _env_first(env_name, legacy) or None


def _supplied_token(request: Request | WebSocket) -> str | None:
    """Token from the new cookie/header, falling back to the pre-rebrand name."""
    headers = request.headers
    cookies = request.cookies
    return (headers.get("x-mia-token") or headers.get("x-jarvis-token")
            or cookies.get("mia_token") or cookies.get("jarvis_token"))


def _request_authed(request: Request) -> bool:
    token = hud_token()
    if not token:
        return True
    # ?token= lets `start-mia.sh` open the HUD already logged in (HUD converts it to a cookie)
    return _supplied_token(request) == token or request.query_params.get("token") == token


@app.middleware("http")
async def api_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and not _request_authed(request):
        return Response(status_code=401, content="mia auth required")
    return await call_next(request)


def _ws_allowed(ws: WebSocket) -> bool:
    """Browsers send Origin (+cookie); native clients (PTT, tests) send neither."""
    origin = ws.headers.get("origin")
    if not origin:
        return True  # non-browser client on the LAN (Python PTT, e2e tests)
    from urllib.parse import urlparse
    origin_host = (urlparse(origin).hostname or "").lower()
    request_host = (ws.headers.get("host") or "").rsplit(":", 1)[0].lower()
    # Same-origin is always fine: opening https://192.168.1.10:8766/hud/ sends
    # exactly that Origin, and the HUD must be able to talk to its own server.
    same_origin = bool(origin_host) and origin_host == request_host
    if not (same_origin or origin_host in ALLOWED_ORIGIN_HOSTS):
        return False
    token = hud_token()
    if not token:
        return True
    return (_supplied_token(ws) == token) or ws.query_params.get("token") == token


# --------------------------------------------------------------- HUD + proxy

HUD_DIR = ROOT / "hud"
ALLOWED_GET_PATHS = {
    "/health", "/health/detailed", "/v1/capabilities",
    "/v1/skills", "/v1/toolsets", "/api/jobs", "/api/sessions",
}


def _proxy_allowed(method: str, path: str) -> bool:
    if method == "GET":
        return path in ALLOWED_GET_PATHS or (
            path.startswith("/api/sessions/") and path.endswith("/messages")
        )
    if method == "POST":
        return path == "/v1/responses"
    return False


@app.api_route("/api/hermes/{path:path}", methods=["GET", "POST"])
async def hermes_proxy(path: str, request: Request) -> Response:
    target = "/" + path
    if not _proxy_allowed(request.method, target):
        return Response(status_code=403, content="path not allowed")
    hermes = HERMES
    body = await request.body()
    params = dict(request.query_params)

    def do_request() -> requests.Response:
        return requests.request(
            request.method, hermes.base + target, params=params,
            headers=hermes.headers(), data=body if body else None, timeout=300,
        )

    resp = await asyncio.to_thread(do_request)
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type=resp.headers.get("Content-Type", "application/json"))


@app.post("/api/chat")
async def hud_chat(request: Request) -> JSONResponse:
    """Typed chat from the HUD — same Hermes session as voice."""
    body = await request.json()
    text = (body.get("input") or "").strip()
    conversation = body.get("conversation") or (CFG.get("hermes") or {}).get("conversation", "mia-main")
    if not text:
        return JSONResponse({"error": "empty input"}, status_code=400)
    out: dict = {"text": "", "tools": [], "run_id": None}

    def run_sync() -> None:
        timeout = float((CFG.get("hermes") or {}).get("timeout", 240))

        def consume(sid: str) -> list[str]:
            parts: list[str] = []
            for kind, value in HERMES.chat_stream_events(sid, text, timeout):
                if kind == "text":
                    parts.append(value)
                elif kind == "tool":
                    out["tools"].append(json.loads(value))
                elif kind == "run":
                    out["run_id"] = value
                elif kind == "final":
                    info = json.loads(value)
                    if info.get("content"):
                        parts = [info["content"]]
            return parts

        try:
            parts = consume(HERMES.get_session_id(conversation))
        except RuntimeError as exc:
            if "404" not in str(exc):
                raise
            # stale session id (e.g. profile switch / DB reset) -> recreate once
            out["tools"].clear()
            parts = consume(HERMES.get_session_id(conversation, force_new=True))
        out["text"] = "".join(parts).strip()

    try:
        await asyncio.to_thread(run_sync)
        return JSONResponse(out)
    except Exception as exc:
        print(f"hud_chat failed: {type(exc).__name__}: {exc}", flush=True)
        return JSONResponse({"error": friendly_error(exc)}, status_code=502)


_ELEVEN_CACHE: dict = {"ts": 0.0, "data": None}


def _tts_provider() -> str:
    tts_cfg = CFG.get("tts") or {}
    provider = (tts_cfg.get("provider") or "").lower()
    if not provider:
        provider = "elevenlabs" if CFG.get("voice") else "piper"
    return provider


def _tts_is_elevenlabs() -> bool:
    return _tts_provider() == "elevenlabs"


def _tts_detail() -> str:
    tts_cfg = CFG.get("tts") or {}
    provider = _tts_provider()
    if provider == "piper":
        return (tts_cfg.get("piper") or {}).get("language") or "piper"
    if provider == "http":
        http = tts_cfg.get("http") or {}
        return http.get("name") or http.get("engine") or "http"
    if provider == "elevenlabs":
        return (CFG.get("voice") or {}).get("model") or "elevenlabs"
    return provider


@app.get("/api/usage")
async def usage() -> JSONResponse:
    """LLM token usage (local tally) + ElevenLabs subscription quota."""
    u = read_usage()
    cost_cfg = CFG.get("usage") or {}
    cin = float(cost_cfg.get("llm_cost_per_mtok_input", 0) or 0)
    cout = float(cost_cfg.get("llm_cost_per_mtok_output", 0) or 0)

    def est(b: dict) -> float | None:
        if not (cin or cout):
            return None
        return round(b.get("llm_in", 0) / 1e6 * cin + b.get("llm_out", 0) / 1e6 * cout, 4)

    out = {
        "llm": {
            "today": u["today"], "total": u["total"],
            "today_cost": est(u["today"]), "total_cost": est(u["total"]),
        },
        "elevenlabs": None,
    }
    # ElevenLabs subscription — only when TTS is actually cloud-based. Local
    # providers must not generate any outbound request.
    now = time.time()
    if not _tts_is_elevenlabs():
        out["elevenlabs"] = None
        return JSONResponse(out)
    if (_ELEVEN_CACHE["data"] is None or now - _ELEVEN_CACHE["ts"] > 300) and not _ELEVEN_CACHE.get("refreshing"):
        key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY") or os.environ.get("XI_API_KEY")
        if key:
            _ELEVEN_CACHE["refreshing"] = True

            def fetch() -> dict | None:
                try:
                    r = requests.get("https://api.elevenlabs.io/v1/user/subscription",
                                     headers={"xi-api-key": key}, timeout=10)
                    if r.ok:
                        j = r.json()
                        return {
                            "used": j.get("character_count"),
                            "limit": j.get("character_limit"),
                            "remaining": (j.get("character_limit") or 0) - (j.get("character_count") or 0),
                            "tier": j.get("tier"),
                            "resets_unix": j.get("next_character_count_reset_unix"),
                        }
                except Exception:
                    pass
                return None

            async def refresh() -> None:
                try:
                    data = await asyncio.to_thread(fetch)
                    if data is not None:
                        _ELEVEN_CACHE.update(ts=time.time(), data=data)
                finally:
                    _ELEVEN_CACHE["refreshing"] = False

            asyncio.get_running_loop().create_task(refresh())
    out["elevenlabs"] = _ELEVEN_CACHE["data"]
    return JSONResponse(out)


WS_CLIENTS: set = set()
ACTIVE_PANELS: set = set()   # src of every holographic panel currently up
LAST_SUMMON: dict = {}       # last media shown — for "odpri predvajanje v brskalniku"


@app.post("/api/summon")
async def summon(request: Request) -> JSONResponse:
    """Broadcast a holographic media panel to all connected HUD clients.

    Body: {"media": "video"|"iframe"|"image", "src": "...", "title": "...",
           "position": "center"|"left"|"right"}  or  {"action": "dismiss"}
    Hermes can call this (curl with X-Mia-Token) to display media on the HUD.
    """
    body = await request.json()
    if body.get("action") == "dismiss":
        ACTIVE_PANELS.clear()
        payload = {"type": "dismiss_panels"}
    else:
        src = body.get("src", "")
        if src:
            ACTIVE_PANELS.add(src)
            LAST_SUMMON.update(media=body.get("media") or body.get("type") or "iframe",
                               src=src, title=body.get("title", ""))
        payload = {"type": "summon_panel",
                   "media": body.get("media") or body.get("type") or "iframe",
                   "src": body.get("src", ""),
                   "title": body.get("title", "INCOMING FEED"),
                   "position": body.get("position", "center")}
    sent = 0
    for client in list(WS_CLIENTS):
        try:
            await client.send_json(payload)
            sent += 1
        except Exception:
            WS_CLIENTS.discard(client)
    return JSONResponse({"sent_to": sent})


_WORKER_CACHE: dict = {"ts": 0.0, "data": [], "refreshing": False}


@app.post("/api/voice-pitch")
async def set_voice_pitch(request: Request) -> JSONResponse:
    """HUD slider: live pitch for the TTS voice, in semitones vs the base voice."""
    body = await request.json()
    semis = max(-12.0, min(12.0, float((body or {}).get("semitones", 0.0))))
    VOICE_SETTINGS["pitch_semitones"] = round(semis, 2)
    VOICE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_SETTINGS_PATH.write_text(json.dumps(VOICE_SETTINGS), encoding="utf-8")
    print(f"voice pitch set to {semis:+.2f} semitones", flush=True)
    return JSONResponse({"pitch_semitones": VOICE_SETTINGS["pitch_semitones"]})


@app.get("/api/hud-config")
async def hud_config() -> JSONResponse:
    """HUD behaviour switches: external media, UI language, TTS provider."""
    hud_cfg = CFG.get("hud") or {}
    stt = CFG.get("stt") or {}
    hermes = CFG.get("hermes") or {}
    return JSONResponse({
        "allow_external_media": bool(hud_cfg.get("allow_external_media", False)),
        "language": stt.get("language") or "en",
        "tts_provider": _tts_provider(),
        "tts_detail": _tts_detail(),
        "stt_model": stt.get("model") or "",
        "stt_device": stt.get("device") or "",
        "fallback_provider": hermes.get("fallback_provider") or "",
        "hermes_url": hermes.get("base_url") or "",
        "conversation": hermes.get("conversation") or "",
        "pitch_semitones": VOICE_SETTINGS.get("pitch_semitones", 0.0),
    })


def _local_gpu() -> dict:
    """Read-only local GPU stats via nvidia-smi; empty dict when unavailable.

    Aggregates all cards: VRAM is summed, utilisation and temperature are the max,
    so a 2-GPU tensor split shows as one row (vram_total = both cards).
    """
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {}
    try:
        out = subprocess.run(
            [smi, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return {}
        utils, temps = [], []
        used = total = 0.0
        for line in out.stdout.splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                utils.append(float(parts[0]))
                used += float(parts[1])
                total += float(parts[2])
            except ValueError:
                continue
            if len(parts) > 3 and parts[3] not in ("[N/A]", "N/A", ""):
                try:
                    temps.append(float(parts[3]))
                except ValueError:
                    pass
        if not utils:
            return {}
        stats = {
            "gpu_count": len(utils),
            "gpu_util": round(max(utils)),
            "vram_used": round(used / 1024, 1),
            "vram_total": round(total / 1024, 1),
        }
        if temps:
            stats["gpu_temp"] = round(max(temps))
        return stats
    except Exception:
        return {}


@app.get("/api/machines")
async def machines() -> JSONResponse:
    """Local (Mac) stats + configured remote workers.

    Worker polls can take seconds when a worker is offline, so they run in a
    background refresh; the endpoint always answers instantly from cache.
    """
    result: list[dict] = []
    mac: dict = {"name": "MAC MINI · HERMES", "online": True}
    if psutil:
        mac.update({
            "cpu": psutil.cpu_percent(interval=0.1),
            "mem": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage(str(ROOT)).percent,
        })
    mac.update(_local_gpu())
    result.append(mac)

    def poll_worker(w: dict) -> dict:
        info = {"name": w.get("name", w.get("host", "worker")), "online": False}
        url = w.get("stats_url")
        if url:
            try:
                r = requests.get(url, timeout=2)
                if r.ok:
                    info.update(r.json())
                    info["online"] = True
                    return info
            except Exception:
                pass
        import socket
        try:
            with socket.create_connection((w.get("host"), int(w.get("ping_port", 445))), timeout=1.5):
                info["online"] = True
                info["note"] = "online (no stats agent)"
        except Exception:
            pass
        return info

    workers = CFG.get("machines") or []
    now = time.time()
    if workers and now - _WORKER_CACHE["ts"] > 10 and not _WORKER_CACHE["refreshing"]:
        _WORKER_CACHE["refreshing"] = True

        async def refresh() -> None:
            try:
                data = [await asyncio.to_thread(poll_worker, w) for w in workers]
                _WORKER_CACHE.update(ts=time.time(), data=data)
            finally:
                _WORKER_CACHE["refreshing"] = False

        asyncio.get_running_loop().create_task(refresh())
    result.extend(_WORKER_CACHE["data"] or
                  [{"name": w.get("name", "worker"), "online": False, "note": "checking..."} for w in workers])
    return JSONResponse({"machines": result})


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse("/hud/")


if HUD_DIR.exists():
    app.mount("/hud", StaticFiles(directory=str(HUD_DIR), html=True), name="hud")


# ----------------------------------------------- Hermes dashboard TLS proxy
# The HUD (https) cannot iframe the plain-http dashboard (mixed content), so
# this second app reverse-proxies the entire dashboard over TLS, stripping
# frame-blocking headers. Served on its own port (see server.dashboard_proxy).

dash_app = FastAPI(title="Hermes Dashboard TLS Proxy")
_STRIP_HEADERS = {"x-frame-options", "content-security-policy", "content-length",
                  "transfer-encoding", "connection", "content-encoding"}


@dash_app.middleware("http")
async def dash_auth_middleware(request: Request, call_next):
    if not _request_authed(request):
        return Response(status_code=401, content="mia auth required")
    return await call_next(request)


def _dash_target() -> str:
    return ((CFG.get("server") or {}).get("dashboard_proxy") or {}).get(
        "target", "http://127.0.0.1:9119").rstrip("/")


@dash_app.websocket("/{path:path}")
async def dash_ws_proxy(ws: WebSocket, path: str) -> None:
    import websockets as wslib
    token = hud_token()
    if token and _supplied_token(ws) != token:
        await ws.close(code=4401)
        return
    await ws.accept()
    target = _dash_target().replace("http://", "ws://").replace("https://", "wss://")
    uri = f"{target}/{path}" + (f"?{ws.url.query}" if ws.url.query else "")
    try:
        async with wslib.connect(uri, max_size=None) as backend:
            async def client_to_backend() -> None:
                while True:
                    m = await ws.receive()
                    if m.get("text") is not None:
                        await backend.send(m["text"])
                    elif m.get("bytes") is not None:
                        await backend.send(m["bytes"])
                    elif m.get("type") == "websocket.disconnect":
                        break

            async def backend_to_client() -> None:
                async for m in backend:
                    if isinstance(m, str):
                        await ws.send_text(m)
                    else:
                        await ws.send_bytes(m)

            done, pending_t = await asyncio.wait(
                [asyncio.create_task(client_to_backend()),
                 asyncio.create_task(backend_to_client())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending_t:
                t.cancel()
    except Exception:
        pass


@dash_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dash_http_proxy(path: str, request: Request) -> Response:
    body = await request.body()
    fwd_headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in ("host", "accept-encoding", "connection")}

    def do_request() -> requests.Response:
        return requests.request(
            request.method, f"{_dash_target()}/{path}",
            params=dict(request.query_params), headers=fwd_headers,
            data=body if body else None, timeout=60, allow_redirects=False,
        )

    resp = await asyncio.to_thread(do_request)
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _STRIP_HEADERS}
    return Response(content=resp.content, status_code=resp.status_code, headers=out_headers)


# ------------------------------------------------------------------ WebSocket


@dataclass
class ConnState:
    audio_chunks: list = field(default_factory=list)
    recording: bool = False
    timing: TurnTiming | None = None
    turn_task: asyncio.Task | None = None
    current_run_id: str | None = None
    conversation: str = "mia-main"
    spoken_sentences: list = field(default_factory=list)
    interrupt_note: str | None = None
    partial_task: asyncio.Task | None = None
    last_partial_bytes: int = 0
    continuous: bool = False
    segmenter: object | None = None
    wake: WakeGate | None = None
    last_reply_at: float | None = None
    is_speaking: bool = False          # TTS audio is streaming right now
    audio_bytes_total: int = 0         # continuous-mode flow diagnostics
    audio_stats_at: float = 0.0
    pending_utterance: bytes | None = None  # said while a turn was busy — runs next
    last_rejected_stt_at: float = 0.0       # debounce for override STT on foreign voices


async def _speak_and_finish(ws: WebSocket, pipeline: VoicePipelineServer,
                            conn: "ConnState", timing: "TurnTiming", text: str) -> None:
    """Speak a fixed confirmation and close the turn — no Hermes involved."""
    conn.spoken_sentences = [text]
    await pipeline._send_tts_sentence(ws, text, timing, conn)
    timing.response_text = text
    timing.total_done_monotonic = time.perf_counter()
    await ws.send_json({"type": "done", "turn_id": timing.turn_id, "timing": timing.summary()})
    conn.last_reply_at = time.time()


async def _run_turn(ws: WebSocket, pipeline: VoicePipelineServer, conn: ConnState,
                    wake: "WakeGate | None" = None) -> None:
    timing = conn.timing
    assert timing is not None
    audio = b"".join(conn.audio_chunks)
    conn.audio_chunks = []
    try:
        # voice calibration: only the enrolled speaker gets through — checked
        # BEFORE the expensive STT so foreign voices cost ~100 ms, not seconds.
        # A failed check still gets transcribed once: an explicit wake word can
        # carry the turn (media override) or trigger voice enrollment.
        gate = pipeline.speaker_gate
        speaker_ok, score = True, None
        if wake is not None and gate is not None and gate.enrolled:
            speaker_ok, score = await asyncio.to_thread(
                gate.verify, np.frombuffer(audio, dtype=np.int16))
            if not speaker_ok:
                # noise must not burn STT: only longer utterances, debounced,
                # get transcribed at all — and then only an EXACT "Mia" may
                # trigger the override paths below
                now_m = time.monotonic()
                if len(audio) < 32000 * 1.2 or now_m - conn.last_rejected_stt_at < 3.0:
                    timing.errors.append(f"ignored: speaker score {score}")
                    await ws.send_json({"type": "ignored", "reason": "speaker"})
                    return
                conn.last_rejected_stt_at = now_m
                print(f"SPEAKER check failed (score={score:.2f}) — STT odloči (budnica/vpis)", flush=True)
        # acknowledge immediately: on CPU the STT alone can take tens of
        # seconds, and silence here reads as "she is not reacting"
        await ws.send_json({"type": "agent_status", "state": "thinking"})
        transcript = await pipeline.transcribe(audio, timing)
        transcript = pipeline.filter_hallucinations(transcript)
        timing.transcript = transcript
        said_wake = bool(transcript) and wake is not None and wake.starts_with_wake(transcript)
        if not speaker_ok:
            # foreign/failed voice: fuzzy wake variants are off the table —
            # only an EXACT "Mia" start may use any override path
            said_wake = bool(transcript) and starts_with_exact_wake(transcript)

        # "Mia, prepoznaj glas!" — append THIS utterance to the voiceprint
        # (works even when the gate just rejected the voice: that is the point,
        # e.g. enrolling how the user sounds from the far side of the room)
        if said_wake and gate is not None and _is_enroll_command(transcript):
            await asyncio.to_thread(
                gate.enroll, [np.frombuffer(audio, dtype=np.int16)], gate.enrolled)
            confirm = "Zapomnjeno, šefe — ta glas zdaj poznam."
            print(f"SPEAKER enrolled from voice command (score was {score})", flush=True)
            await _speak_and_finish(ws, pipeline, conn, timing, confirm)
            return

        # deterministic media control — works in any session, and (because it
        # only needs the wake word) even while loud playback drowns the voiceprint
        if said_wake and _is_media_stop(transcript):
            await _stop_all_media()
            print(f"MEDIA stopped via voice: {transcript[:60]!r}", flush=True)
            await _speak_and_finish(ws, pipeline, conn, timing, "Ustavljeno, šefe.")
            return
        if said_wake and _is_media_open_browser(transcript):
            src = LAST_SUMMON.get("src") or ""
            await _stop_all_media()
            if src:
                await asyncio.to_thread(subprocess.run, ["mia-open", src],
                                        capture_output=True, timeout=20)
                confirm = "Odprla sem ga v brskalniku, šefe."
            else:
                confirm = "Ni aktivnega predvajanja, šefe."
            print(f"MEDIA open-in-browser via voice: {src or 'nič'}", flush=True)
            await _speak_and_finish(ws, pipeline, conn, timing, confirm)
            return

        if said_wake:
            _, stripped = wake.check(transcript, None, time.time())
        else:
            stripped = transcript
        vol_args = _volume_request(stripped) if said_wake else None
        if vol_args is not None:
            r = await asyncio.to_thread(subprocess.run, ["mia-volume", *vol_args],
                                        capture_output=True, text=True, timeout=10)
            lines = (r.stdout or "").strip().splitlines()
            last = lines[-1] if lines else ""
            if "glasnost:" in last:
                confirm = f"Glasnost {last.split(':', 1)[1].strip()}, šefe."
            else:
                confirm = "Zvok preklopljen, šefe."
            print(f"VOLUME via voice: {' '.join(vol_args)} -> {last}", flush=True)
            await _speak_and_finish(ws, pipeline, conn, timing, confirm)
            return

        music_query = _music_play_request(stripped) if said_wake else None
        if music_query is not None:
            query = music_query or _pick_favorite_artist()
            # one song at a time: the new order immediately stops the old one
            await _stop_all_media()

            def _find_on_youtube() -> tuple[str, str] | None:
                try:
                    r = subprocess.run(
                        ["yt-dlp", f"ytsearch1:{query}", "--get-title", "--get-id",
                         "--no-playlist"],
                        capture_output=True, text=True, timeout=30)
                except Exception:
                    return None
                lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
                return (lines[0], lines[1]) if len(lines) >= 2 else None

            found = await asyncio.to_thread(_find_on_youtube)
            if not found:
                print(f"MUSIC search failed for {query!r}", flush=True)
                await _speak_and_finish(ws, pipeline, conn, timing,
                                        "Nisem našla ničesar, šefe.")
                return
            title, vid = found
            src = f"https://www.youtube.com/watch?v={vid}"
            try:
                with (Path.home() / ".cache" / "mia-history.log").open("a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M')}\t{src}\n")
            except OSError:
                pass
            sent = await _summon_media(src, title)
            if sent == 0:  # no HUD connected: play in a desktop window instead
                await asyncio.to_thread(subprocess.run, ["mia-open", src],
                                        capture_output=True, timeout=20)
            print(f"MUSIC playing ({query!r}): {title[:60]} [{vid}]", flush=True)
            await _speak_and_finish(ws, pipeline, conn, timing, "Evo šefe.")
            return

        if not speaker_ok:
            gate_cfg = ((pipeline.cfg["stt"].get("continuous") or {}).get("speaker_gate") or {})
            override = (said_wake and bool(gate_cfg.get("wake_override", True))
                        and await asyncio.to_thread(_playback_active))
            if override:
                print(f"SPEAKER override accepted via wake word: {transcript[:80]!r}", flush=True)
            else:
                timing.errors.append(f"ignored: speaker score {score}")
                await ws.send_json({"type": "ignored", "reason": "speaker"})
                return
        await ws.send_json({"type": "transcript", "text": transcript})
        if transcript and wake is not None:
            accept, transcript = wake.check(transcript, conn.last_reply_at, time.time())
            if not accept:
                timing.errors.append("ignored: no wake word")
                print(f"WAKE rejected: {transcript[:100]!r}", flush=True)
                await ws.send_json({"type": "ignored", "reason": "wake", "text": transcript})
                return
            timing.transcript = transcript
            print(f"WAKE accepted: {transcript[:100]!r}", flush=True)
        if not transcript:
            if wake is not None:
                return  # continuous mode: empty/noise utterances are normal, stay quiet
            await ws.send_json({"type": "error", "message": "No transcript detected."})
        else:
            if conn.interrupt_note:
                transcript_sent = (
                    f"[note: your previous spoken reply was cut off by the user after you said: "
                    f"\"{conn.interrupt_note}\"]\n{transcript}"
                )
                conn.interrupt_note = None
            else:
                transcript_sent = transcript
            conn.spoken_sentences = []
            await pipeline.stream_response_audio(ws, transcript_sent, timing, conn)
            timing.total_done_monotonic = time.perf_counter()
            await ws.send_json({"type": "done", "turn_id": timing.turn_id, "timing": timing.summary()})
            if timing.response_text:
                # the follow-up window opens only after a REAL reply — phantom
                # turns (noise, hallucinations) must not unlock wake-free speech
                conn.last_reply_at = time.time()
    except asyncio.CancelledError:
        timing.errors.append("turn cancelled (barge-in or stop)")
        raise
    except Exception as exc:
        timing.errors.append(f"{type(exc).__name__}: {exc}")
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        timing.total_done_monotonic = timing.total_done_monotonic or time.perf_counter()
        pipeline.log_turn(timing)
        conn.timing = None
        conn.current_run_id = None
        conn.is_speaking = False


async def _continuous_turn(ws: WebSocket, pipeline: VoicePipelineServer, conn: ConnState) -> None:
    """One utterance from the always-on stream: same turn logic, wake-gated."""
    try:
        await _run_turn(ws, pipeline, conn, wake=conn.wake)
    finally:
        if conn.continuous:
            pending, conn.pending_utterance = conn.pending_utterance, None
            if pending:
                _start_continuous_turn(ws, pipeline, conn, pending)
                return
            try:
                await ws.send_json({"type": "status", "message": "continuous listening"})
            except Exception:
                pass


def _start_continuous_turn(ws: WebSocket, pipeline: VoicePipelineServer, conn: ConnState,
                           pcm: bytes) -> None:
    conn.audio_chunks = [pcm]
    conn.recording = False
    conn.timing = TurnTiming(turn_id=pipeline.next_turn_id())
    conn.timing.audio_start_monotonic = time.perf_counter()
    conn.timing.stt_model = CFG["stt"]["model"]
    conn.turn_task = asyncio.create_task(_continuous_turn(ws, pipeline, conn))


async def _feed_continuous(ws: WebSocket, pipeline: VoicePipelineServer, conn: ConnState,
                           chunk: bytes) -> None:
    """Feed the always-on stream through the VAD and start turns automatically."""
    barge = bool(((CFG.get("stt") or {}).get("continuous") or {}).get("barge_in", True))
    conn.audio_bytes_total += len(chunk)
    now = time.time()
    if now - conn.audio_stats_at >= 10:
        conn.audio_stats_at = now
        seg = conn.segmenter
        print(f"continuous audio flowing: {conn.audio_bytes_total / 32000:.0f}s total, "
              f"vad_prob={getattr(seg, 'prob', 0):.2f}, state={getattr(seg, 'state', '?')}",
              flush=True)
    prev_state = getattr(conn.segmenter, "state", "silence")
    events = conn.segmenter.feed(chunk)
    new_state = getattr(conn.segmenter, "state", "silence")
    if new_state != prev_state:
        try:
            await ws.send_json({"type": "vad", "state": new_state,
                                "prob": round(float(getattr(conn.segmenter, "prob", 0.0)), 2)})
        except Exception:
            pass
    for kind, payload in events:
        busy = conn.turn_task is not None and not conn.turn_task.done()
        if kind == "speech_start":
            if busy:
                if not barge:
                    continue        # half-duplex: ignore the speaker's own echo
                if not conn.is_speaking:
                    # mid-thinking: a click or noise burst must not kill the turn;
                    # deliberate speech still barges via its completed "utterance"
                    continue
                await _cancel_active_turn(ws, pipeline, conn)   # barge-in
                await ws.send_json({"type": "agent_status", "state": "stopped"})
            await ws.send_json({"type": "agent_status", "state": "listening"})
            continue
        if kind == "utterance":
            if busy:
                if not barge:
                    # half-duplex: don't kill the turn — queue the utterance
                    # (newest wins) and run it as soon as the turn finishes
                    conn.pending_utterance = payload
                    print("utterance queued (turn busy)", flush=True)
                    continue
                await _cancel_active_turn(ws, pipeline, conn)
            _start_continuous_turn(ws, pipeline, conn, payload)


async def _cancel_active_turn(ws: WebSocket, pipeline: VoicePipelineServer, conn: ConnState,
                              stop_remote: bool = True) -> None:
    run_id = conn.current_run_id  # capture BEFORE cancel: turn cleanup clears it
    turn_was_active = conn.turn_task is not None and not conn.turn_task.done()
    if turn_was_active:
        if conn.spoken_sentences:
            conn.interrupt_note = conn.spoken_sentences[-1]
        conn.turn_task.cancel()
        try:
            await conn.turn_task
        except (asyncio.CancelledError, Exception):
            pass
    if stop_remote and run_id and turn_was_active:
        conn.current_run_id = None
        try:
            res = await asyncio.to_thread(pipeline.hermes.stop_run, run_id)
            # 404 = session runs not in the runs registry on this Hermes build;
            # dropping the SSE stream (above) still cuts the turn off.
            msg = "Run halted." if res["status_code"] in (200, 202, 404) else f"Stop returned {res['status_code']}."
            await ws.send_json({"type": "status", "message": msg})
        except Exception as exc:
            await ws.send_json({"type": "status", "message": f"Stop failed: {exc}"})


def _maybe_schedule_partial(ws: WebSocket, pipeline: VoicePipelineServer, conn: ConnState) -> None:
    stt_cfg = CFG.get("stt") or {}
    if not stt_cfg.get("partials", True) or not conn.recording:
        return
    if conn.partial_task and not conn.partial_task.done():
        return
    buf = b"".join(conn.audio_chunks)
    min_new = int(16000 * 2 * float(stt_cfg.get("partial_interval", 1.2)))
    if len(buf) < 16000 or len(buf) - conn.last_partial_bytes < min_new or len(buf) > 16000 * 2 * 30:
        return
    conn.last_partial_bytes = len(buf)

    async def run() -> None:
        try:
            text = await pipeline.transcribe(buf)
            if text and conn.recording:
                await ws.send_json({"type": "partial_transcript", "text": text})
        except Exception:
            pass

    conn.partial_task = asyncio.create_task(run())


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    if not _ws_allowed(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    WS_CLIENTS.add(ws)
    pipeline = get_pipeline()
    conn = ConnState(conversation=(CFG.get("hermes") or {}).get("conversation", "mia-main"))
    await ws.send_json({"type": "status", "message": "Hermes voice server connected."})
    try:
        while True:
            message = await ws.receive()
            if "text" in message and message["text"] is not None:
                event = json.loads(message["text"])
                etype = event.get("type")
                if etype == "start":
                    await _cancel_active_turn(ws, pipeline, conn)  # barge-in
                    if event.get("conversation"):
                        conn.conversation = str(event["conversation"])
                    conn.audio_chunks = []
                    conn.last_partial_bytes = 0
                    conn.recording = True
                    cont_cfg = dict(((CFG.get("stt") or {}).get("continuous") or {}))
                    if str(event.get("mode") or "").lower() == "continuous":
                        conn.continuous = True
                        conn.segmenter = build_segmenter(cont_cfg)
                        conn.wake = WakeGate(cont_cfg.get("wake_words"),
                                             float(cont_cfg.get("followup_seconds", 20)))
                        await ws.send_json({
                            "type": "status",
                            "message": "continuous listening",
                            "vad": getattr(conn.segmenter.detector, "kind", "?"),
                            "wake_words": conn.wake.words,
                        })
                        continue
                    conn.continuous = False
                    conn.segmenter = None
                    conn.timing = TurnTiming(turn_id=pipeline.next_turn_id())
                    conn.timing.audio_start_monotonic = time.perf_counter()
                    conn.timing.stt_model = CFG["stt"]["model"]
                    await ws.send_json({"type": "status", "message": f"Turn {conn.timing.turn_id} recording started."})
                elif etype == "stop":
                    if conn.continuous:
                        conn.continuous = False
                        conn.recording = False
                        pending = conn.segmenter.flush() if conn.segmenter else []
                        conn.segmenter = None
                        await ws.send_json({"type": "status", "message": "continuous listening stopped"})
                        for kind, payload in pending:
                            if kind == "utterance":
                                _start_continuous_turn(ws, pipeline, conn, payload)
                        continue
                    if conn.timing is None:
                        await ws.send_json({"type": "error", "message": "Received stop before start."})
                        continue
                    conn.recording = False
                    conn.timing.end_of_speech_monotonic = time.perf_counter()
                    conn.turn_task = asyncio.create_task(_run_turn(ws, pipeline, conn))
                elif etype == "flush":
                    if not conn.continuous or conn.segmenter is None:
                        await ws.send_json({"type": "error", "message": "flush only in continuous mode"})
                        continue
                    barge = bool(((CFG.get("stt") or {}).get("continuous") or {}).get("barge_in", True))
                    started = False
                    for kind, payload in conn.segmenter.flush():
                        if kind != "utterance":
                            continue
                        if conn.turn_task is not None and not conn.turn_task.done():
                            if not barge:
                                continue    # half-duplex: never kill a running turn
                            await _cancel_active_turn(ws, pipeline, conn)
                        _start_continuous_turn(ws, pipeline, conn, payload)
                        started = True
                    await ws.send_json({"type": "status",
                                        "message": "utterance submitted" if started else "nothing to submit"})
                elif etype == "panel_closed":
                    ACTIVE_PANELS.discard(str(event.get("src") or ""))
                elif etype == "stop_run":
                    await _cancel_active_turn(ws, pipeline, conn)
                    await ws.send_json({"type": "agent_status", "state": "stopped"})
                elif etype == "approval_decision":
                    run_id = event.get("run_id") or conn.current_run_id
                    if not run_id:
                        await ws.send_json({"type": "error", "message": "No run for approval."})
                        continue
                    decision = event.get("decision", "deny")
                    body = {
                        "decision": decision,
                        "approved": decision == "allow",
                        "approval_id": event.get("approval_id"),
                    }
                    res = await asyncio.to_thread(pipeline.hermes.post_approval, run_id, body)
                    await ws.send_json({"type": "status", "message": f"Approval sent ({res['status_code']})."})
                else:
                    await ws.send_json({"type": "error", "message": f"Unknown event type: {etype}"})
            elif "bytes" in message and message["bytes"] is not None:
                if conn.continuous and conn.segmenter is not None:
                    await _feed_continuous(ws, pipeline, conn, message["bytes"])
                elif conn.recording:
                    conn.audio_chunks.append(message["bytes"])
                    _maybe_schedule_partial(ws, pipeline, conn)
    except (WebSocketDisconnect, WebSocketDisconnected):
        conn.continuous = False
        if conn.turn_task and not conn.turn_task.done():
            conn.turn_task.cancel()
        print("Client disconnected", flush=True)
    except RuntimeError as exc:
        # newer starlette raises this instead of WebSocketDisconnect when the
        # client vanishes mid-receive — same cleanup, no traceback
        if "disconnect" not in str(exc).lower():
            raise
        conn.continuous = False
        if conn.turn_task and not conn.turn_task.done():
            conn.turn_task.cancel()
        print("Client disconnected", flush=True)
    finally:
        WS_CLIENTS.discard(ws)


def main() -> int:
    server = CFG["server"]
    host = server.get("host", "0.0.0.0")
    port = int(server.get("port", 8765))
    tls_ports = server.get("tls_ports") or ([server["tls_port"]] if server.get("tls_port") else [])
    cert = server.get("tls_cert")
    key = server.get("tls_key")
    print(f"Starting Hermes voice server on ws://{host}:{port}/ws", flush=True)
    if tls_ports and cert and key and (ROOT / cert).exists() and (ROOT / key).exists():
        servers = [uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))]
        for tp in tls_ports:
            print(f"HUD available on https://{host}:{tp}/hud/", flush=True)
            servers.append(uvicorn.Server(uvicorn.Config(
                app, host=host, port=int(tp), log_level="info",
                ssl_certfile=str(ROOT / cert), ssl_keyfile=str(ROOT / key),
            )))

        dp = server.get("dashboard_proxy") or {}
        if dp.get("port"):
            print(f"Dashboard proxy on https://{host}:{dp['port']}/", flush=True)
            servers.append(uvicorn.Server(uvicorn.Config(
                dash_app, host=host, port=int(dp["port"]), log_level="warning",
                ssl_certfile=str(ROOT / cert), ssl_keyfile=str(ROOT / key),
            )))

        async def serve_one(srv) -> None:
            # One listener must never take down the others: binding :443 as a
            # non-root user fails, and gather() would then cancel every port.
            try:
                await srv.serve()
            except BaseException as exc:  # noqa: BLE001 - SystemExit/KeyboardInterrupt included
                port = getattr(getattr(srv, "config", None), "port", "?")
                hint = ""
                try:
                    if int(port) < 1024 and os.geteuid() != 0:
                        hint = (" (privileged port: run as root, or set server.tls_ports: [8766] "
                                "and open https://HOST:8766/hud/)")
                except (TypeError, ValueError):
                    pass
                print(f"listener on :{port} stopped: {exc!r}{hint}", flush=True)

        async def serve_all() -> None:
            await asyncio.gather(*[serve_one(s) for s in servers])

        asyncio.run(serve_all())
    else:
        uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
